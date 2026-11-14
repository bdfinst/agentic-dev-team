import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  Injectable,
  OnInit,
  computed,
  inject,
  signal,
} from "@angular/core";
import { AsyncPipe, CurrencyPipe, DatePipe } from "@angular/common";
import { HttpClient, HttpParams } from "@angular/common/http";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { ActivatedRoute, Router } from "@angular/router";
import {
  BehaviorSubject,
  Observable,
  combineLatest,
  debounceTime,
  distinctUntilChanged,
  map,
  shareReplay,
  switchMap,
} from "rxjs";

export type OrderStatus = "pending" | "paid" | "shipped" | "cancelled";

export interface Order {
  readonly id: string;
  readonly customerName: string;
  readonly status: OrderStatus;
  readonly totalCents: number;
  readonly placedAt: string;
}

export interface OrderQuery {
  readonly status: OrderStatus | "all";
  readonly search: string;
  readonly page: number;
}

export interface OrderPage {
  readonly orders: readonly Order[];
  readonly totalCount: number;
}

const PAGE_SIZE = 25;
const SEARCH_DEBOUNCE_MS = 300;

@Injectable({ providedIn: "root" })
export class OrderApi {
  private readonly http = inject(HttpClient);

  list(query: OrderQuery): Observable<OrderPage> {
    const params = new HttpParams()
      .set("status", query.status)
      .set("search", query.search)
      .set("page", query.page)
      .set("pageSize", PAGE_SIZE);
    return this.http.get<OrderPage>("/api/orders", { params });
  }

  cancel(orderId: string): Observable<Order> {
    return this.http.post<Order>(`/api/orders/${orderId}/cancel`, {});
  }
}

@Injectable({ providedIn: "root" })
export class AlertFeed {
  private readonly unread = new BehaviorSubject<number>(0);
  readonly unreadCount$ = this.unread.asObservable();

  publish(count: number): void {
    this.unread.next(count);
  }
}

@Injectable({ providedIn: "root" })
export class OrderSelection {
  private readonly selected = signal<readonly string[]>([]);
  readonly selectedIds = this.selected.asReadonly();
  readonly count = computed(() => this.selected().length);

  toggle(orderId: string): void {
    this.selected.update((ids) =>
      ids.includes(orderId)
        ? ids.filter((id) => id !== orderId)
        : [...ids, orderId],
    );
  }

  clear(): void {
    this.selected.set([]);
  }
}

function toQuery(params: Record<string, string | undefined>): OrderQuery {
  const status = (params["status"] as OrderStatus | undefined) ?? "all";
  const page = Number(params["page"] ?? "1");
  return {
    status,
    search: params["search"] ?? "",
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

function summarize(orders: readonly Order[]): {
  paidCents: number;
  pending: number;
} {
  return orders.reduce(
    (totals, order) => ({
      paidCents:
        totals.paidCents + (order.status === "paid" ? order.totalCents : 0),
      pending: totals.pending + (order.status === "pending" ? 1 : 0),
    }),
    { paidCents: 0, pending: 0 },
  );
}

@Component({
  selector: "app-order-dashboard",
  standalone: true,
  imports: [AsyncPipe, CurrencyPipe, DatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="toolbar">
      <input
        type="search"
        placeholder="Search customers"
        [value]="searchTerm()"
        (input)="onSearch($any($event.target).value)"
      />
      <select
        [value]="statusFilter()"
        (change)="onStatus($any($event.target).value)"
      >
        <option value="all">All</option>
        <option value="pending">Pending</option>
        <option value="paid">Paid</option>
        <option value="shipped">Shipped</option>
        <option value="cancelled">Cancelled</option>
      </select>
      <span class="alerts">{{ unreadAlerts() }} unread alerts</span>
      <span class="selection">{{ selection.count() }} selected</span>
    </header>

    @if (page$ | async; as page) {
      <section class="summary">
        <span>Paid: {{ summaryOf(page).paidCents / 100 | currency }}</span>
        <span>Pending: {{ summaryOf(page).pending }}</span>
      </section>
      <table>
        @for (order of page.orders; track order.id) {
          <tr
            [class.selected]="isSelected(order.id)"
            (click)="selection.toggle(order.id)"
          >
            <td>{{ order.customerName }}</td>
            <td>{{ order.status }}</td>
            <td>{{ order.totalCents / 100 | currency }}</td>
            <td>{{ order.placedAt | date: "medium" }}</td>
            <td>
              @if (order.status === "pending") {
                <button (click)="cancel(order.id); $event.stopPropagation()">
                  Cancel
                </button>
              }
            </td>
          </tr>
        }
      </table>
      <footer>
        <button
          [disabled]="currentPage() === 1"
          (click)="goToPage(currentPage() - 1)"
        >
          Previous
        </button>
        <span
          >Page {{ currentPage() }} of {{ pageCount(page.totalCount) }}</span
        >
        <button
          [disabled]="currentPage() >= pageCount(page.totalCount)"
          (click)="goToPage(currentPage() + 1)"
        >
          Next
        </button>
      </footer>
    }
  `,
})
export class OrderDashboardComponent implements OnInit {
  private readonly api = inject(OrderApi);
  private readonly alerts = inject(AlertFeed);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  readonly selection = inject(OrderSelection);

  readonly searchTerm = signal("");
  readonly statusFilter = signal<OrderStatus | "all">("all");
  readonly currentPage = signal(1);
  readonly unreadAlerts = signal(0);

  private readonly refresh$ = new BehaviorSubject<void>(undefined);
  private readonly search$ = new BehaviorSubject<string>("");

  readonly query$: Observable<OrderQuery> = this.route.queryParams.pipe(
    map((params) => toQuery(params)),
    distinctUntilChanged(
      (a, b) =>
        a.status === b.status && a.search === b.search && a.page === b.page,
    ),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  readonly page$: Observable<OrderPage> = combineLatest([
    this.query$,
    this.refresh$,
  ]).pipe(
    switchMap(([query]) => this.api.list(query)),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  ngOnInit(): void {
    this.query$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((query) => {
      this.searchTerm.set(query.search);
      this.statusFilter.set(query.status);
      this.currentPage.set(query.page);
    });

    this.search$
      .pipe(
        debounceTime(SEARCH_DEBOUNCE_MS),
        distinctUntilChanged(),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((search) => this.navigate({ search, page: 1 }));

    this.alerts.unreadCount$.subscribe((count) => this.unreadAlerts.set(count));
  }

  onSearch(term: string): void {
    this.searchTerm.set(term);
    this.search$.next(term);
  }

  onStatus(status: OrderStatus | "all"): void {
    this.navigate({ status, page: 1 });
  }

  goToPage(page: number): void {
    this.navigate({ page });
  }

  cancel(orderId: string): void {
    this.api
      .cancel(orderId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.refresh$.next());
  }

  isSelected(orderId: string): boolean {
    return this.selection.selectedIds().includes(orderId);
  }

  summaryOf(page: OrderPage): { paidCents: number; pending: number } {
    return summarize(page.orders);
  }

  pageCount(totalCount: number): number {
    return Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  }

  private navigate(changes: Partial<OrderQuery>): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: changes,
      queryParamsHandling: "merge",
    });
  }
}
