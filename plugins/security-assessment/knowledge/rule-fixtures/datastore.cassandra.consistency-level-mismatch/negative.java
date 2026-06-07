class Repo {
  void run() {
    writeStmt.setConsistencyLevel(ConsistencyLevel.QUORUM);
    readStmt.setConsistencyLevel(ConsistencyLevel.QUORUM);
  }
}
