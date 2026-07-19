// Lazy singleton init with an await gap between the existence check and the
// assignment: two concurrent callers both see undefined and both construct,
// so the resource is initialized twice (connection leak / lost state).
interface Conn {
  close(): Promise<void>;
}

let conn: Conn | undefined;

async function openConn(): Promise<Conn> {
  // expensive async connect
  return {} as Conn;
}

export async function getConn(): Promise<Conn> {
  if (conn === undefined) {
    // BUG: the await yields the event loop; a second caller passes the same
    // undefined check before conn is assigned, so openConn() runs twice.
    conn = await openConn();
  }
  return conn;
}
