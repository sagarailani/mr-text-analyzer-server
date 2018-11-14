from collections import defaultdict
from enum import Enum
from os import path
import sys

from spellchecker.editdistance import DistanceAlgorithm, EditDistance
import spellchecker.helpers as helpers

class Verbosity(Enum):
    TOP = 0
    CLOSEST = 1
    ALL = 2

class SpellChecker(object):
    def __init__(self, initial_capacity=16, max_dictionary_edit_distance=2,
                 prefix_length=7, count_threshold=1, compact_level=5):
        if initial_capacity < 0:
            raise ValueError("initial_capacity cannot be negative")
        if max_dictionary_edit_distance < 0:
            raise ValueError("max_dictionary_edit_distance cannot be negative")
        if prefix_length < 1 or prefix_length <= max_dictionary_edit_distance:
            raise ValueError("prefix_length cannot be less than 1 or "
                             "smaller than max_dictionary_edit_distance")
        if count_threshold < 0:
            raise ValueError("count_threshold cannot be negative")
        if compact_level < 0 or compact_level > 16:
            raise ValueError("compact_level must be between 0 and 16")
        self._initial_capacity = initial_capacity
        self._words = dict()
        self._below_threshold_words = dict()
        self._deletes = defaultdict(list)
        self._max_dictionary_edit_distance = max_dictionary_edit_distance
        self._prefix_length = prefix_length
        self._count_threshold = count_threshold
        self._compact_mask = (0xFFFFFFFF >> (3 + min(compact_level, 16))) << 2
        self._distance_algorithm = DistanceAlgorithm.DAMERUAUOSA
        self._max_length = 0

    def create_dictionary_entry(self, key, count):
        if count <= 0:
            if self._count_threshold > 0:
                return False
            count = 0
        if self._count_threshold > 1 and key in self._below_threshold_words:
            count_previous = self._below_threshold_words[key]
            count = (count_previous + count
                     if sys.maxsize - count_previous > count
                     else sys.maxsize)
            if count >= self._count_threshold:
                self._below_threshold_words.pop(key)
            else:
                self._below_threshold_words[key] = count
                return False
        elif key in self._words:
            count_previous = self._words[key]
            count = (count_previous + count
                     if sys.maxsize - count_previous > count
                     else sys.maxsize)
            self._words[key] = count
            return False
        elif count < self._count_threshold:
            self._below_threshold_words[key] = count
            return False

        self._words[key] = count

        if len(key) > self._max_length:
            self._max_length = len(key)

        edits = self.edits_prefix(key)
        for delete in edits:
            delete_hash = self.get_str_hash(delete)
            if delete_hash in self._deletes:
                self._deletes[delete_hash].append(key)
            else:
                self._deletes[delete_hash] = [key]
        return True

    def load_dictionary(self, corpus, term_index, count_index):
        if not path.exists(corpus):
            return False
        with open(corpus, "r") as infile:
            for line in infile:
                line_parts = line.rstrip().split(" ")
                if len(line_parts) >= 2:
                    key = line_parts[term_index]
                    count = helpers.try_parse_int64(line_parts[count_index])
                    if count is not None:
                        self.create_dictionary_entry(key, count)
        return True

    def lookup(self, phrase, verbosity, max_edit_distance=None,
               include_unknown=False):
        if max_edit_distance is None:
            max_edit_distance = self._max_dictionary_edit_distance
        if max_edit_distance > self._max_dictionary_edit_distance:
            raise ValueError("Distance too large")
        suggestions = list()
        phrase_len = len(phrase)
        def early_exit():
            if include_unknown and not suggestions:
                suggestions.append(SuggestItem(phrase, max_edit_distance + 1,
                                               0))
            return suggestions
        if phrase_len - max_edit_distance > self._max_length:
            return early_exit()

        suggestion_count = 0
        if phrase in self._words:
            suggestion_count = self._words[phrase]
            suggestions.append(SuggestItem(phrase, 0, suggestion_count))
            if verbosity != Verbosity.ALL:
                return early_exit()

        if max_edit_distance == 0:
            return early_exit()

        considered_deletes = set()
        considered_suggestions = set()
        considered_suggestions.add(phrase)

        max_edit_distance_2 = max_edit_distance
        candidate_pointer = 0
        candidates = list()

        phrase_prefix_len = phrase_len
        if phrase_prefix_len > self._prefix_length:
            phrase_prefix_len = self._prefix_length
            candidates.append(phrase[: phrase_prefix_len])
        else:
            candidates.append(phrase)
        distance_comparer = EditDistance(self._distance_algorithm)
        while candidate_pointer < len(candidates):
            candidate = candidates[candidate_pointer]
            candidate_pointer += 1
            candidate_len = len(candidate)
            len_diff = phrase_prefix_len - candidate_len

            if len_diff > max_edit_distance_2:
                if verbosity == Verbosity.ALL:
                    continue
                break

            if self.get_str_hash(candidate) in self._deletes:
                dict_suggestions = self._deletes[self.get_str_hash(candidate)]
                for suggestion in dict_suggestions:
                    if suggestion == phrase:
                        continue
                    suggestion_len = len(suggestion)
                    if (abs(suggestion_len - phrase_len) > max_edit_distance_2
                            or suggestion_len < candidate_len
                            or (suggestion_len == candidate_len
                                and suggestion != candidate)):
                        continue
                    suggestion_prefix_len = min(suggestion_len,
                                                self._prefix_length)
                    if (suggestion_prefix_len > phrase_prefix_len
                            and suggestion_prefix_len - candidate_len > max_edit_distance_2):
                        continue
                    distance = 0
                    min_distance = 0
                    if candidate_len == 0:
                        distance = max(phrase_len, suggestion_len)
                        if (distance > max_edit_distance_2
                                or suggestion in considered_suggestions):
                            continue
                    elif suggestion_len == 1:
                        distance = (phrase_len
                                    if phrase.index(suggestion[0]) < 0
                                    else phrase_len - 1)
                        if (distance > max_edit_distance_2
                                or suggestion in considered_suggestions):
                            continue
                    else:
                        if self._prefix_length - max_edit_distance == candidate_len:
                            min_distance = (min(phrase_len, suggestion_len) -
                                            self._prefix_length)
                        else:
                            min_distance = 0
                        if (self._prefix_length - max_edit_distance == candidate_len
                                and (min_distance > 1
                                     and phrase[phrase_len + 1 - min_distance :] != suggestion[suggestion_len + 1 - min_distance :])
                                or (min_distance > 0
                                    and phrase[phrase_len - min_distance] != suggestion[suggestion_len - min_distance]
                                    and (phrase[phrase_len - min_distance - 1] != suggestion[suggestion_len - min_distance]
                                         or phrase[phrase_len - min_distance] != suggestion[suggestion_len - min_distance - 1]))):
                            continue
                        else:
                            if ((verbosity != Verbosity.ALL
                                 and not self.delete_in_suggestion_prefix(
                                     candidate, candidate_len, suggestion,
                                     suggestion_len))
                                    or suggestion in considered_suggestions):
                                continue
                            considered_suggestions.add(suggestion)
                            distance = distance_comparer.compare(
                                phrase, suggestion, max_edit_distance_2)
                            if distance < 0:
                                continue
                    if distance <= max_edit_distance_2:
                        suggestion_count = self._words[suggestion]
                        si = SuggestItem(suggestion, distance, suggestion_count)
                        if suggestions:
                            if verbosity == Verbosity.CLOSEST:
                                if distance < max_edit_distance_2:
                                    suggestions = list()
                            elif verbosity == Verbosity.TOP:
                                if (distance < max_edit_distance_2
                                        or suggestion_count > suggestions[0].count):
                                    max_edit_distance_2 = distance
                                    suggestions[0] = si
                                continue
                        if verbosity != Verbosity.ALL:
                            max_edit_distance_2 = distance
                        suggestions.append(si)
            if (len_diff < max_edit_distance
                    and candidate_len <= self._prefix_length):
                if (verbosity != Verbosity.ALL
                        and len_diff >= max_edit_distance_2):
                    continue
                for i in range(candidate_len):
                    delete = candidate[: i] + candidate[i + 1 :]
                    if delete not in considered_deletes:
                        considered_deletes.add(delete)
                        candidates.append(delete)
        if len(suggestions) > 1:
            suggestions.sort()
        return suggestions

    def lookup_compound(self, phrase, max_edit_distance,
                        ignore_non_words=False):
        term_list_1 = helpers.parse_words(phrase)
        if ignore_non_words:
            term_list_2 = helpers.parse_words(phrase, True)
        suggestions = list()
        suggestion_parts = list()
        distance_comparer = EditDistance(self._distance_algorithm)

        is_last_combi = False
        for i, __ in enumerate(term_list_1):
            if ignore_non_words:
                if helpers.try_parse_int64(term_list_1[i]) is not None:
                    suggestion_parts.append(SuggestItem(term_list_1[i], 0, 0))
                    continue
                if helpers.is_acronym(term_list_2[i]):
                    suggestion_parts.append(SuggestItem(term_list_2[i], 0, 0))
                    continue
            suggestions = self.lookup(term_list_1[i], Verbosity.TOP,
                                      max_edit_distance)
            if i > 0 and not is_last_combi:
                suggestions_combi = self.lookup(
                    term_list_1[i - 1] + term_list_1[i], Verbosity.TOP,
                    max_edit_distance)
                if suggestions_combi:
                    best_1 = suggestion_parts[-1]
                    if suggestions:
                        best_2 = suggestions[0]
                    else:
                        best_2 = SuggestItem(term_list_1[i],
                                             max_edit_distance + 1, 0)
                    distance_1 = distance_comparer.compare(
                        term_list_1[i - 1] + " " + term_list_1[i],
                        best_1.term.lower() + " " + best_2.term,
                        max_edit_distance)
                    if (distance_1 >= 0
                            and suggestions_combi[0].distance + 1 < distance_1):
                        suggestions_combi[0].distance += 1
                        suggestion_parts[-1] = suggestions_combi[0]
                        is_last_combi = True
                        continue
            is_last_combi = False

            if (suggestions and (suggestions[0].distance == 0
                                 or len(term_list_1[i]) == 1)):
                suggestion_parts.append(suggestions[0])
            else:
                suggestions_split = list()
                if suggestions:
                    suggestions_split.append(suggestions[0])
                if len(term_list_1[i]) > 1:
                    for j in range(1, len(term_list_1[i])):
                        part_1 = term_list_1[i][: j]
                        part_2 = term_list_1[i][j :]
                        suggestions_1 = self.lookup(part_1, Verbosity.TOP,
                                                    max_edit_distance)
                        if suggestions_1:
                            if (suggestions
                                    and suggestions[0].term == suggestions_1[0].term):
                                break
                            suggestions_2 = self.lookup(part_2, Verbosity.TOP,
                                                        max_edit_distance)
                            if suggestions_2:
                                if (suggestions
                                        and suggestions[0].term == suggestions_2[0].term):
                                    break
                                tmp_term = (suggestions_1[0].term + " " +
                                            suggestions_2[0].term)
                                tmp_distance = distance_comparer.compare(
                                    term_list_1[i], tmp_term,
                                    max_edit_distance)
                                if tmp_distance < 0:
                                    tmp_distance = max_edit_distance + 1
                                tmp_count = min(suggestions_1[0].count,
                                                suggestions_2[0].count)
                                suggestion_split = SuggestItem(
                                    tmp_term, tmp_distance, tmp_count)
                                suggestions_split.append(suggestion_split)
                                if suggestion_split.distance == 1:
                                    break

                    if suggestions_split:
                        suggestions_split.sort()
                        suggestion_parts.append(suggestions_split[0])
                    else:
                        si = SuggestItem(term_list_1[i],
                                         max_edit_distance + 1, 0)
                        suggestion_parts.append(si)
                else:
                    si = SuggestItem(term_list_1[i], max_edit_distance + 1, 0)
                    suggestion_parts.append(si)
        joined_term = ""
        joined_count = sys.maxsize
        for si in suggestion_parts:
            joined_term += si.term + " "
            joined_count = min(joined_count, si.count)
        suggestion = SuggestItem(joined_term.rstrip(),
                                 distance_comparer.compare(
                                     phrase, joined_term, 2 ** 31 - 1),
                                 joined_count)
        suggestions_line = list()
        suggestions_line.append(suggestion)
        return suggestions_line

    def delete_in_suggestion_prefix(self, delete, delete_len, suggestion,
                                    suggestion_len):
        if delete_len == 0:
            return True
        if self._prefix_length < suggestion_len:
            suggestion_len = self._prefix_length
        j = 0
        for i in range(delete_len):
            del_char = delete[i]
            while j < suggestion_len and del_char != suggestion[j]:
                j += 1
            if j == suggestion_len:
                return False
        return True

    def edits(self, word, edit_distance, delete_words):
        edit_distance += 1
        if len(word) > 1:
            for i in range(len(word)):
                delete = word[: i] + word[i + 1 :]
                if delete not in delete_words:
                    delete_words.add(delete)
                    if edit_distance < self._max_dictionary_edit_distance:
                        self.edits(delete, edit_distance, delete_words)
        return delete_words

    def edits_prefix(self, key):
        hash_set = set()
        if len(key) <= self._max_dictionary_edit_distance:
            hash_set.add("")
        if len(key) > self._max_dictionary_edit_distance:
            key = key[: self._prefix_length]
        hash_set.add(key)
        return self.edits(key, 0, hash_set)

    def get_str_hash(self, s):
        s_len = len(s)
        mask_len = min(s_len, 3)

        hash_s = 2166136261
        for i in range(s_len):
            hash_s ^= ord(s[i])
            hash_s *= 16777619
        hash_s &= self._compact_mask
        hash_s |= mask_len
        return hash_s

    @property
    def deletes(self):
        return self._deletes

    @property
    def words(self):
        return self._words

    @property
    def word_count(self):
        return len(self._words)

class SuggestItem(object):
    def __init__(self, term, distance, count):
        self._term = term
        self._distance = distance
        self._count = count

    def __eq__(self, other):
        if self._distance == other.distance:
            return self._count == other.count
        else:
            return self._distance == other.distance

    def __lt__(self, other):
        if self._distance == other.distance:
            return self._count > other.count
        else:
            return self._distance < other.distance

    def __str__(self):
        return "{}, {}, {}".format(self._term, self._distance, self._count)

    @property
    def term(self):
        return self._term

    @term.setter
    def term(self, term):
        self._term = term

    @property
    def distance(self):
        return self._distance

    @distance.setter
    def distance(self, distance):
        self._distance = distance

    @property
    def count(self):
        return self._count

    @count.setter
    def count(self, count):
        self._count = count