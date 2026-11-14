CREATE TABLE customers (
    id          bigint       NOT NULL PRIMARY KEY,
    email       varchar(320) NOT NULL,
    created_at  timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE orders (
    id           bigint      NOT NULL PRIMARY KEY,
    customer_id  bigint      NOT NULL REFERENCES customers (id),
    status       varchar(20) NOT NULL,
    placed_at    timestamp   NOT NULL,
    cancelled_at timestamp   NULL
);

CREATE TABLE shipments (
    id          bigint      NOT NULL PRIMARY KEY,
    order_id    bigint      NOT NULL REFERENCES orders (id),
    carrier     varchar(40) NOT NULL,
    tracking_no varchar(64) NULL,
    shipped_at  timestamp   NOT NULL
);

CREATE TABLE refunds (
    id         bigint        NOT NULL PRIMARY KEY,
    order_id   bigint        NULL,
    amount     numeric(12,2) NOT NULL,
    created_at timestamp     NOT NULL
);
