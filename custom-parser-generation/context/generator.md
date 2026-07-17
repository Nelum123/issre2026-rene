### Specification

This file lists all the specficiations relating to the "grammar generator".

The output file is named `grammar_gen.py`.

### Process

- The LL(1) context-free grammar can have the following example structure:

```
{ "$start": [["a", "$A"], ["b", "$B*"]],
"$A": [["a"]],
"$B": [["b"]]
}
```

- `*` means that 0 or more occurences of the character is allowed. `+` means that 1 or more occurences of the character is allowed.
- The generator takes an input JSON file created by `converter.py` and produce a grammar JSON file.
- The symbols used for the terminals are characters from `a-z`, and can be randomized.
- The symbols used for the non-terminals are `$D` + numbers starting from 1 (e.g. `$D1`, `$D2`).
- All the grammar generated must be LL(1) and do not have unreachable non-terminals.
- The grammar must have statistics matching the input file exactly.

### Generator Input

The grammar parameters are all of the following:

- nts_per_depth: the number of non-terminals per depth (min = 0)
- rules_per_def: the number of rules per definition. (min = 1)
- rule_len: the length of the rules. (min = 1)
- nt_per_rule: the number of non-terminals per rule. (min = 0)
- star_count: the total number of `*` used in the grammar. (min = 0)
- plus_count: the total number of `+` used in the grammar. (min = 0)

### Additional Rules

- `*` and `+` can only be placed after non-terminals (e.g. `$D1*`, `$D2+`) but NOT terminals (e.g. `a+` is prohibited).
- Do not place multiple copies of the same non-terminal (with or without `*` or `+`) in the same bracket. For instance, this construction is invalid:

```json
[
  "o",
  "$D1",
  "$D1",
  "$D1",
  "e"
],
```

### Minimum Output

```json
{
  "$start": [["a"]]
}
```

### Testing

Once any work is done on the generator, do the following steps:

- Generate 100 random input json files, containing a random number of specific statistics from the statistics list above.
- For each of those input files, generate a grammar file using the generator.
- Check the grammar for exactly the following information, no more or less:
  - The grammar follows the examples above.
  - The grammar is LL(1).
  - The grammar does not have any unreachable non-terminals.
  - The grammar matches the fields in its input exactly, without randomization except for terminal and non-terminal symbols.
  - The accepted error margin between the accepted statistics and the input statistics is 5%, rounded down (e.g. if input "halstead_N2": 252 is given, then the output "halstead_N2": 239 ~ 264). Any value outside that range would count the test case as failed.