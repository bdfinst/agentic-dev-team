from matrix import matmul, identity, transpose
assert matmul([[1,2],[3,4]],[[5,6],[7,8]]) == [[19,22],[43,50]]
assert matmul([[1,2],[3,4]], identity(2)) == [[1,2],[3,4]]
assert transpose([[1,2,3],[4,5,6]]) == [[1,4],[2,5],[3,6]]
print("OK")
