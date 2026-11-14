import {
  Component,
  DestroyRef,
  NgZone,
  OnInit,
  inject,
  signal,
} from "@angular/core";
import { AsyncPipe, DatePipe } from "@angular/common";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { Observable } from "rxjs";

import { SyncStatus, SyncService } from "./sync.service";

const POLL_INTERVAL_MS = 15_000;

@Component({
  selector: "app-sync-indicator",
  standalone: true,
  imports: [AsyncPipe, DatePipe],
  template: `
    @if (status$ | async; as status) {
      <span class="status" [class.status--error]="status.failed">
        {{ status.label }}
      </span>
    }
    <time>Last checked {{ lastCheckedAt | date: "shortTime" }}</time>
    <span class="pending">{{ pendingCount() }} pending</span>
  `,
})
export class SyncIndicatorComponent implements OnInit {
  private readonly zone = inject(NgZone);
  private readonly sync = inject(SyncService);
  private readonly destroyRef = inject(DestroyRef);

  readonly status$: Observable<SyncStatus> = this.sync.status$;
  readonly pendingCount = signal(0);
  lastCheckedAt: Date | null = null;

  ngOnInit(): void {
    this.sync.pending$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((count) => this.pendingCount.set(count));

    // Polling runs outside the zone so the 15-second timer does not trigger
    // application-wide change detection on every tick.
    this.zone.runOutsideAngular(() => {
      const timerId = setInterval(() => {
        this.sync.checkNow();
        this.lastCheckedAt = new Date();
      }, POLL_INTERVAL_MS);
      this.destroyRef.onDestroy(() => clearInterval(timerId));
    });
  }
}
