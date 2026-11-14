import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  DestroyRef,
  EventEmitter,
  Input,
  NgZone,
  Output,
  computed,
  effect,
  inject,
  signal,
} from "@angular/core";
import { AsyncPipe } from "@angular/common";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { fromEvent, map, switchMap } from "rxjs";

import { Product, ProductService } from "./product.service";

export interface ProductFilter {
  readonly query: string;
  readonly inStockOnly: boolean;
}

const FILTER_STORAGE_KEY = "product-list.filter";

@Component({
  selector: "app-product-list",
  standalone: true,
  imports: [AsyncPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <input (input)="setQuery($any($event.target).value)" [value]="filter().query" />
    <ul>
      @for (product of visibleProducts(); track product.id) {
        <li (click)="select(product)">{{ product.name }}</li>
      }
    </ul>
    <p>Viewport width: {{ viewportWidth }}</p>
    <p>{{ (recommendations$ | async)?.length ?? 0 }} recommendations</p>
  `,
})
export class ProductListComponent {
  private readonly products = inject(ProductService);
  private readonly zone = inject(NgZone);
  private readonly changeDetector = inject(ChangeDetectorRef);
  private readonly destroyRef = inject(DestroyRef);

  @Input({ required: true }) set items(value: readonly Product[]) {
    this.allProducts.set(value);
  }
  @Output() readonly selected = new EventEmitter<Product>();

  readonly allProducts = signal<readonly Product[]>([]);
  readonly filter = signal<ProductFilter>({ query: "", inStockOnly: false });
  readonly selectedIds = signal<readonly string[]>([]);

  readonly visibleProducts = computed(() => {
    const { query, inStockOnly } = this.filter();
    const matches = this.allProducts().filter(
      (product) =>
        product.name.toLowerCase().includes(query.toLowerCase()) &&
        (!inStockOnly || product.stock > 0),
    );
    const sorted = [...matches];
    sorted.sort((a, b) => a.name.localeCompare(b.name));
    return sorted;
  });

  readonly recommendations$ = this.products.selection$.pipe(
    switchMap((ids) => this.products.recommendationsFor(ids)),
  );

  viewportWidth = window.innerWidth;

  constructor() {
    effect(() => {
      localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(this.filter()));
    });

    this.zone.runOutsideAngular(() => {
      fromEvent(window, "resize")
        .pipe(
          map(() => window.innerWidth),
          takeUntilDestroyed(this.destroyRef),
        )
        .subscribe((width) => {
          this.zone.run(() => {
            this.viewportWidth = width;
            this.changeDetector.markForCheck();
          });
        });
    });
  }

  setQuery(query: string): void {
    this.filter.update((current) => ({ ...current, query }));
  }

  toggleInStockOnly(): void {
    this.filter.update((current) => ({ ...current, inStockOnly: !current.inStockOnly }));
  }

  select(product: Product): void {
    this.selectedIds.update((ids) => [...ids, product.id]);
    this.selected.emit(product);
  }
}
