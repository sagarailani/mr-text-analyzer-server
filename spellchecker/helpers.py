import re

def null_distance_results(string1, string2, max_distance):
    if string1 is None:
        if string2 is None:
            return 0
        else:
            return len(string2) if len(string2) <= max_distance else -1
    return len(string1) if len(string1) <= max_distance else -1

def prefix_suffix_prep(string1, string2):
    len1 = len(string1)
    len2 = len(string2)
    while len1 != 0 and string1[len1 - 1] == string2[len2 - 1]:
        len1 -= 1
        len2 -= 1
    start = 0
    while start != len1 and string1[start] == string2[start]:
        start += 1
    if start != 0:
        len1 -= start
        len2 -= start
    return len1, len2, start

def to_similarity(distance, length):
    return -1 if distance < 0 else 1.0 - distance / length

def try_parse_int64(string):
    try:
        ret = int(string)
    except ValueError:
        return None
    return None if ret < -2 ** 64 or ret >= 2 ** 64 else ret

def parse_words(phrase, preserve_case=False):
    if preserve_case:
        return re.findall(r"([^\W_]+['’]*[^\W_]*)", phrase)
    else:
        return re.findall(r"([^\W_]+['’]*[^\W_]*)", phrase.lower())

def is_acronym(word):
    return re.match(r"\b[A-Z0-9]{2,}\b", word) is not None

