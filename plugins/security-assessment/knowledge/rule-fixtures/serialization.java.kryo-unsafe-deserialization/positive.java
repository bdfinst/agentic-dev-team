class D {
  Object run(Kryo kryo, Input in) {
    return kryo.readObject(in, Foo.class);
  }
}
