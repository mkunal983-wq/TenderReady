"""Source-declared hardware baselines; no inferred performance ranking."""
import re


def baseline_match(actual, expected):
    normalize = lambda value: ' '.join(value.casefold().split())
    value, baseline = normalize(actual), normalize(expected)
    # These are alternatives explicitly written in the clause, not benchmarks.
    if baseline == 'intel hd 4400 or above/discrete graphics':
        return value in {'intel hd 4400', 'discrete graphics'}
    return value == baseline


def hardware_baseline(segment):
    match = re.fullmatch(r'Processor:\s*(5th Generation Intel Core i5) or above[.;]?', segment, re.I)
    if match:
        return 'processor', match[1]
    match = re.fullmatch(r'Graphics:\s*(Intel HD (?:6000|4400)) or above[.;]?', segment, re.I)
    if match:
        return 'graphics', match[1]
    match = re.fullmatch(r'Graphics:\s*(Intel HD 4400 or above/Discrete Graphics)[.;]?', segment, re.I)
    if match:
        return 'graphics', match[1]
    return None
