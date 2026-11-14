import {
  computed,
  reactive,
  ref,
  type ComputedRef,
  type Ref,
} from "vue";

export interface CartLine {
  readonly sku: string;
  readonly name: string;
  readonly unitPriceCents: number;
  readonly quantity: number;
}

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

export function useFormattedPrice(amountCents: number): ComputedRef<string> {
  return computed(() => currencyFormatter.format(amountCents / 100));
}

export function useCart(initialLines: readonly CartLine[] = []) {
  const state = reactive({
    lines: [...initialLines] as CartLine[],
    couponCode: "",
  });
  const lastChangedSku: Ref<string | null> = ref(null);

  const subtotalCents = computed(() =>
    state.lines.reduce(
      (sum, line) => sum + line.unitPriceCents * line.quantity,
      0,
    ),
  );
  const itemCount = computed(() =>
    state.lines.reduce((sum, line) => sum + line.quantity, 0),
  );

  const formattedSubtotal = useFormattedPrice(subtotalCents.value);

  function setQuantity(sku: string, quantity: number): void {
    state.lines = state.lines
      .map((line) => (line.sku === sku ? { ...line, quantity } : line))
      .filter((line) => line.quantity > 0);
    lastChangedSku.value = sku;
  }

  function addLine(line: CartLine): void {
    const existing = state.lines.find(
      (candidate) => candidate.sku === line.sku,
    );
    if (existing) {
      setQuantity(line.sku, existing.quantity + line.quantity);
      return;
    }
    state.lines = [...state.lines, line];
    lastChangedSku.value = line.sku;
  }

  function applyCoupon(code: string): void {
    state.couponCode = code.trim().toUpperCase();
  }

  return {
    state,
    itemCount,
    subtotalCents,
    formattedSubtotal,
    lastChangedSku,
    setQuantity,
    addLine,
    applyCoupon,
  };
}
