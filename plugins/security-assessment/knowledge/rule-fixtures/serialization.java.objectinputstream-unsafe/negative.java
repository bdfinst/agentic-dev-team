class D {
  Object run(ObjectInputStream ois) {
    ois.setObjectInputFilter(filter);
    return ois.readObject();
  }
}
