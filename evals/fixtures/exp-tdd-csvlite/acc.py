from csvlite import parse
assert parse("a,b,c") == [["a","b","c"]]
assert parse("a,b\nc,d") == [["a","b"],["c","d"]]
assert parse('"a,b",c') == [["a,b","c"]]
assert parse('"she said ""hi""",x') == [['she said "hi"',"x"]]
assert parse("") == []
print("OK")
