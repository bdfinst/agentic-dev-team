// PASS: Angular OnPush component with immutable update and managed subscription

import {
  Component,
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  OnInit,
  OnDestroy,
  Input,
} from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

interface Item {
  id: number;
  name: string;
}

@Component({
  selector: 'app-item-list',
  template: `<li *ngFor="let item of items">{{ item.name }}</li>`,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ItemListComponent implements OnInit, OnDestroy {
  @Input() items: Item[] = [];

  private destroy$ = new Subject<void>();

  constructor(
    private http: HttpClient,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit() {
    this.http
      .get<Item[]>('/api/items')
      .pipe(takeUntil(this.destroy$)) // subscription auto-cancels on destroy
      .subscribe(result => {
        // New array reference triggers OnPush change detection
        this.items = [...this.items, ...result];
        this.cdr.markForCheck();
      });
  }

  ngOnDestroy() {
    this.destroy$.next();
    this.destroy$.complete();
  }
}
