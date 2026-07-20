// FAIL: OnPush + in-place mutation, unclosed RxJS subscription, effect self-write

import { Component, ChangeDetectionStrategy, Input, OnInit, OnDestroy } from "@angular/core";
import { signal, effect } from "@angular/core";
import { interval, Subscription } from "rxjs";

@Component({
  selector: "app-feed",
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span>{{ items.length }}</span>`,
})
export class FeedComponent implements OnInit, OnDestroy {
  @Input() items: string[] = [];

  // ISSUE: mutating the @Input array in place inside an OnPush component —
  // change detection only checks reference identity and will never re-render
  addItem(next: string) {
    this.items.push(next);
  }

  private sub?: Subscription;

  // ISSUE: subscribe() in ngOnInit with no unsubscribe() in ngOnDestroy —
  // subscription leak on every component destroy/recreate
  ngOnInit() {
    this.sub = interval(1000).subscribe(() => {
      this.addItem(`tick-${Date.now()}`);
    });
  }

  ngOnDestroy() {
    // no this.sub.unsubscribe() here
  }

  // ISSUE: effect() reads `counter` and writes back to `counter` unconditionally
  // -> infinite update loop
  counter = signal(0);
  private loopingEffect = effect(() => {
    this.counter.set(this.counter() + 1);
  });
}
