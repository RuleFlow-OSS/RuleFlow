def test(*args):
    print(args)

test(*(i for i in range(10)))
