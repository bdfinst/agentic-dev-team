def apply_discount(total, tier):
    if tier == 'gold':
        return total * 0.9
    return total

def label(x):
    return str(x)
