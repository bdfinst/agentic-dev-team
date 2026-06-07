class Repo {
  void run() {
    update.ifExists();
    ResultSet rs = session.execute(select);
    session.execute(update);
  }
}
