// FAIL: Angular OnPush + in-place mutation + RxJS subscription leak

import {
  Component,
  ChangeDetectionStrategy,
  OnInit,
  OnDestroy,
  Input,
} from '@angular/core';
import { HttpClient } from '@angular/common/http';

interface Item {
  id: number;
  name: string;
}

@Component({
  selector: 'app-item-list',
  template: `<li *ngFor="let item of items">{{ item.name }}</li>`,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ItemListComponent implements OnInit {
  @Input() items: Item[] = [];

  constructor(private http: HttpClient) {}

  ngOnInit() {
    // ISSUE: RxJS subscription leak — no unsubscribe / takeUntil / async pipe.
    // When this component is destroyed the subscription keeps firing and
    // attempts to update the now-destroyed component.
    this.http.get<Item[]>('/api/items').subscribe(result => {
      // ISSUE: OnPush + in-place mutation — Angular only checks input reference
      // identity with OnPush. Pushing into the existing array doesn't change the
      // reference, so the view never re-renders.
      // Fix: assign a new array reference: this.items = [...this.items, ...result];
      // AND call cdr.markForCheck() or switch to async pipe.
      result.forEach(item => this.items.push(item));
    });
  }
}
