class Repo {
  void run() {
    writeStmt.setConsistencyLevel(ConsistencyLevel.ONE);
    readStmt.setConsistencyLevel(ConsistencyLevel.QUORUM);
  }
}
