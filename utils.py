def is_cjk(text):
    for char in text:
        hex = ord(char)
        if not (0x4e00 <= hex <= 0x9fff or \
            0x3400 <= hex <= 0x4dbf or \
            0x20000 <= hex <= 0x2a6dd or \
            0x2a700 <= hex <= 0x2b73f or \
            0x2b740 <= hex <= 0x2b81f or \
            0x2b820 <= hex <= 0x2ceaf or \
            0x2ceb0 <= hex <= 0x2ebef or \
            0x30000 <= hex <= 0x3134f):
            return False
    return True

def full_width(text):
    chars = []
    for char in text:
        if 0x0021 <= ord(char) <= 0x007e and not char.isalnum():
            chars.append(chr(ord(char) + 0xfee0))
        else:
            chars.append(char)
    return ''.join(chars)