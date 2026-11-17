// PASS: OnPush + immutable updates, takeUntilDestroyed cleanup, correct Signal usage

import { Component, ChangeDetectionStrategy, input, inject, DestroyRef } from "@angular/core";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { signal, computed, effect } from "@angular/core";
import { interval } from "rxjs";

interface Config {
  multiplier: number;
}

@Component({
  selector: "app-counter",
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span>{{ doubled() }}</span>
    <ul>
      @for (item of items(); track $index) {
        <li>{{ item }}</li>
      }
    </ul>
  `,
})
export class CounterComponent {
  // Correct: signal input, so computed() below re-runs when the parent passes a new config
  config = input<Config>({ multiplier: 1 });

  private destroyRef = inject(DestroyRef);

  // Correct: signal wraps a primitive, updated via set()/update() with a new value
  count = signal(0);
  doubled = computed(() => this.count() * this.config().multiplier);
  items = signal<readonly string[]>([]);

  // Correct: effect reads `count` and performs a non-signal side effect — no signal writes
  private persistEffect = effect(() => {
    sessionStorage.setItem("counter", String(this.count()));
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

  // Correct: replaces the array reference instead of mutating in place
  addItem(next: string): void {
    this.items.update((items) => [...items, next]);
  }
}
