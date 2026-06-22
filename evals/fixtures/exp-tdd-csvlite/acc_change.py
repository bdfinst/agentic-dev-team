from csvlite import parse, to_csv
assert to_csv([["a","b","c"]]) == "a,b,c"
assert to_csv([["a,b","c"]]) == '"a,b",c'
assert to_csv([['she said "hi"',"x"]]) == '"she said ""hi""",x'
assert parse('"a,b",c') == [["a,b","c"]]
print("OK")
