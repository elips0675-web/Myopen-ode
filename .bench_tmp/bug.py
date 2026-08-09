def divide(a, b):
    try:
        if b == 0: return None; return a / b
    except ZeroDivisionError:
        return None  # BUG: division by zero possible
print(divide(1, 0))
