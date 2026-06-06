class D {
  Object run(Kryo kryo, Input in) {
    kryo.setRegistrationRequired(true);
    kryo.register(Foo.class);
    return kryo.readObject(in, Foo.class);
  }
}
