#!/usr/bin/env python3
"""Scaffold a xunit.v2 Stryker shim beside a real xunit.v3 test project.

The shim is a second test project that recompiles the SAME test sources under
xunit.v2 (classic VSTest), which Stryker.NET can observe — xunit.v3 runs on the
Microsoft Testing Platform and yields a false ~0% mutation score (stryker-net
issues 3237/3629/3094). This script performs the mechanical part of the howto
(references/shim-howto.md, step 3 + step 6): it reads the real test .csproj and
emits the shim .csproj and a stryker-config.json.

It deliberately does NOT port v3-only source constructs (step 4) — that needs
judgment. Run the scope probe first (see SKILL.md) and port anything it flags in
the REAL test project's sources before building the shim.

Usage:
    python3 generate_shim.py <path-to-real-test.csproj> [--mutate-exclude GLOB ...]

Writes <real-dir>/../<Name>.Mutation/<Name>.Mutation.csproj and stryker-config.json,
then prints the next steps. Stdlib only.
"""
import argparse
import json
import os
import re
import sys


def read(path):
    with open(path, encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def main():
    ap = argparse.ArgumentParser(description="Scaffold a xunit.v2 Stryker shim.")
    ap.add_argument("csproj", help="path to the real xunit.v3 test .csproj")
    ap.add_argument("--mutate-exclude", action="append", default=[],
                    help="extra mutate exclude glob (repeatable), e.g. '**/gRPC/**/*.cs'")
    ap.add_argument("--compile-exclude", action="append", default=[],
                    help="operator-selected v3-feature test file to drop from the shim's "
                         "<Compile> set (repeatable), from the #1160 always-ask gate. Path "
                         "relative to the real project, e.g. '..\\Foo.Tests\\ExplicitTests.cs'")
    args = ap.parse_args()

    real = os.path.abspath(args.csproj)
    if not os.path.isfile(real):
        sys.exit(f"error: no such file: {real}")
    xml = read(real)
    if "xunit.v3" not in xml:
        sys.exit("error: this .csproj does not reference xunit.v3 — a shim is only needed "
                 "for xunit.v3 projects. Nothing to do.")

    real_dir = os.path.dirname(real)
    name = os.path.splitext(os.path.basename(real))[0]
    shim_dir = os.path.join(os.path.dirname(real_dir), name + ".Mutation")
    shim_csproj = os.path.join(shim_dir, name + ".Mutation.csproj")

    tfm = (re.search(r"<TargetFramework>([^<]+)</TargetFramework>", xml) or [None, "net10.0"])[1]
    ns = (re.search(r"<RootNamespace>([^<]+)</RootNamespace>", xml) or [None, name])[1]

    pkgs = re.findall(r"<PackageReference\b[^>]*?/>|<PackageReference\b.*?</PackageReference>",
                      xml, re.DOTALL)
    # Keep every non-xunit dependency verbatim; the xunit stack + Test.Sdk are replaced below.
    kept = [p for p in pkgs if "xunit" not in p.lower() and "Microsoft.NET.Test.Sdk" not in p]
    projrefs = re.findall(r"<ProjectReference\b[^>]*?/>|<ProjectReference\b.*?</ProjectReference>",
                          xml, re.DOTALL)
    if not projrefs:
        print("warning: the real test .csproj has no <ProjectReference> to the product — "
              "add the product reference to the shim manually.", file=sys.stderr)

    lines = ['<Project Sdk="Microsoft.NET.Sdk">', "",
             f"  <!-- xunit.v2 Stryker shim of {name}. Keep out of the .sln and CI test discovery.",
             "       Delete once stryker-net fixes MTP mutation observation (issues 3237/3629/3094). -->", "",
             "  <PropertyGroup>",
             f"    <TargetFramework>{tfm}</TargetFramework>",
             "    <IsPackable>false</IsPackable>",
             f"    <RootNamespace>{ns}</RootNamespace>",
             f"    <AssemblyName>{name}.Mutation</AssemblyName>",
             "    <CopyLocalLockFileAssemblies>true</CopyLocalLockFileAssemblies>",
             "    <NoWarn>$(NoWarn);IDE0028;RCS1163;CS8032;NU1701</NoWarn>",
             "    <GenerateProgramFile>true</GenerateProgramFile>",
             "  </PropertyGroup>", "",
             "  <ItemGroup>",
             '    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.1" />',
             '    <PackageReference Include="xunit" Version="2.9.2" />',
             '    <PackageReference Include="xunit.runner.visualstudio" Version="2.8.2">',
             "      <PrivateAssets>all</PrivateAssets>",
             "      <IncludeAssets>runtime; build; native; contentfiles; analyzers; buildtransitive</IncludeAssets>",
             "    </PackageReference>"]
    lines += ["    " + " ".join(p.split()) for p in kept]
    lines += ["  </ItemGroup>", ""]
    if projrefs:
        lines += ["  <ItemGroup>"]
        lines += ["    " + " ".join(pr.split()) for pr in projrefs]
        lines += ["  </ItemGroup>", ""]
    # Always exclude build output; append operator-selected v3-feature files
    # (#1160) so the shim compiles without the constructs that break under v2.
    compile_excludes = [f"..\\{name}\\obj\\**\\*.cs", f"..\\{name}\\bin\\**\\*.cs"]
    compile_excludes += [g.strip() for g in args.compile_exclude if g.strip()]
    exclude_attr = ";".join(compile_excludes)
    lines += ["  <ItemGroup>",
              f'    <Compile Include="..\\{name}\\**\\*.cs"',
              f'             Exclude="{exclude_attr}">',
              "      <Link>Linked\\%(RecursiveDir)%(FileName)%(Extension)</Link>",
              "    </Compile>",
              "  </ItemGroup>", "", "</Project>", ""]

    os.makedirs(shim_dir, exist_ok=True)
    with open(shim_csproj, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    mutate = ["**/*.cs", "!obj/**/*.cs"] + [f"!{g}" for g in args.mutate_exclude]
    # Pin test-projects to the shim and deliberately set NO SolutionPath: with
    # both set, Stryker enumerates the solution and prefers the real xunit.v3
    # project over the shim (the SolutionPath trap, #557/#1156) — so the shim's
    # kills never register. test-projects alone keeps Stryker on the shim.
    config = {"stryker-config": {
        "test-projects": [f"{name}.Mutation.csproj"],
        "mutate": mutate,
        "mutation-level": "Standard",
        "coverage-analysis": "perTest",
        "additional-timeout": 30000,
        "target-framework": tfm,
        "reporters": ["html", "json", "progress"],
        "thresholds": {"high": 80, "low": 60, "break": 0},
    }}
    config_path = os.path.join(shim_dir, "stryker-config.json")
    with open(config_path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)

    rel = os.path.relpath(shim_dir)
    print(f"Wrote {os.path.relpath(shim_csproj)}")
    print(f"Wrote {os.path.relpath(config_path)}")
    print()
    print("Next (see SKILL.md / references/shim-howto.md):")
    print(f'  1. If the product uses InternalsVisibleTo, add [assembly: InternalsVisibleTo("{name}.Mutation")].')
    print(f"  2. Green baseline:  dotnet build {rel} -c Release  &&  dotnet test {rel} -c Release --no-build")
    print(f"     (expect the SAME test count as {name}, 0 failed)")
    print(f"  3. Kills-register gate: scope mutate to one small covered file, then  cd {rel} && dotnet-stryker")
    print(f"  4. Widen mutate, then run the full mutation FROM the shim dir:  cd {rel} && dotnet-stryker")


if __name__ == "__main__":
    main()
