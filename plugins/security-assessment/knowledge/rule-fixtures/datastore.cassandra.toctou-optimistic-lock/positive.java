class Repo {
  void run() {
    ResultSet rs = session.execute(select);
    session.execute(update);
  }
}
