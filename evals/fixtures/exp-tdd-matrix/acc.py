from matrix import transpose, add, identity
assert transpose([[1,2,3],[4,5,6]]) == [[1,4],[2,5],[3,6]]
assert add([[1,2],[3,4]],[[5,6],[7,8]]) == [[6,8],[10,12]]
assert identity(3) == [[1,0,0],[0,1,0],[0,0,1]]
assert identity(1) == [[1]]
print("OK")
