// PASS: OnPush + immutable updates, takeUntilDestroyed cleanup, correct Signal usage

import { Component, ChangeDetectionStrategy, Input, inject, DestroyRef } from "@angular/core";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { signal, computed, effect } from "@angular/core";
import { interval } from "rxjs";

interface Config {
  multiplier: number;
}

@Component({
  selector: "app-counter",
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span>{{ doubled() }}</span>`,
})
export class CounterComponent {
  @Input() config!: Config;

  private destroyRef = inject(DestroyRef);

  // Correct: signal wraps a primitive, updated via set()/update() with a new value
  count = signal(0);
  doubled = computed(() => this.count() * (this.config?.multiplier ?? 1));

  // Correct: effect only reads `count`, writes to a *different* signal
  lastUpdated = signal<number | null>(null);
  private logEffect = effect(() => {
    const value = this.count();
    this.lastUpdated.set(Date.now());
    void value;
  });

  // Correct: RxJS subscription cleaned up via takeUntilDestroyed — no manual
  // ngOnDestroy bookkeeping needed
  constructor() {
    interval(1000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.count.update((c) => c + 1);
      });
  }

  // Correct: replaces the reference instead of mutating in place, so OnPush
  // change detection sees a new identity
  addItem(items: readonly string[], next: string): string[] {
    return [...items, next];
  }
}
