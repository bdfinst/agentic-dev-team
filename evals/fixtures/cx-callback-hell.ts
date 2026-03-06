// FAIL: Nested callbacks, unstructured promise chains, complex async flow

interface ApiResponse<T> {
  status: number;
  data: T;
}

function fetchUser(id: string, cb: (err: Error | null, data?: any) => void) {
  setTimeout(() => {
    cb(null, { id, name: "Alice" });
  }, 100);
}

function fetchOrders(userId: string, cb: (err: Error | null, data?: any) => void) {
  setTimeout(() => {
    cb(null, [{ orderId: "o1", total: 50 }]);
  }, 100);
}

function fetchShipping(orderId: string, cb: (err: Error | null, data?: any) => void) {
  setTimeout(() => {
    cb(null, { carrier: "UPS", eta: "2 days" });
  }, 100);
}

function getUserOrderDetails(userId: string, cb: (err: Error | null, result?: any) => void) {
  fetchUser(userId, (err, user) => {
    if (err) {
      cb(err);
    } else {
      fetchOrders(user.id, (err2, orders) => {
        if (err2) {
          cb(err2);
        } else {
          const details: any[] = [];
          let pending = orders.length;
          if (pending === 0) {
            cb(null, { user, orders: [] });
          }
          orders.forEach((order: any) => {
            fetchShipping(order.orderId, (err3, shipping) => {
              if (err3) {
                cb(err3);
              } else {
                details.push({ ...order, shipping });
                pending--;
                if (pending === 0) {
                  cb(null, { user, orders: details });
                }
              }
            });
          });
        }
      });
    }
  });
}

function loadDashboard(userId: string): Promise<any> {
  return new Promise((resolve) => {
    return fetch(`/api/users/${userId}`)
      .then((res) => res.json())
      .then((user) => {
        return fetch(`/api/users/${user.id}/prefs`)
          .then((res) => res.json())
          .then((prefs) => {
            return fetch(`/api/users/${user.id}/notifications`)
              .then((res) => res.json())
              .then((notifs) => {
                resolve({ user, prefs, notifications: notifs });
              });
          });
      });
  });
}
