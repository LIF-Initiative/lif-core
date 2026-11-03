# JSONata Quick Start Guide for MDR Mappings

Quick start for creating, testing, and modifying JSONata transformations from a source data model to a LIF target model in the MDR.

Use this guide to create, test, and modify JSONata transformations from a source data model to a LIF target data model in the MetaData Repository (MDR).

## What JSONata does in LIF

JSONata is the expression language LIF uses to turn source JSON into target JSON. In the MDR, a mapping connects a source attribute to a target attribute and stores a JSONata expression that produces the target structure.

Think of a transformation as:

```text
source JSON + JSONata expression = LIF-shaped JSON fragment
```

The LIF Translator runs the expressions in a mapping group and deep-merges their object-shaped results into one output record. The output must conform to the selected target model.

## Create your first mapping

1. Open Mappings in the MDR.
2. Select the source data model and target LIF data model.
3. Select an existing mapping group, or choose + Create to create one.
4. Connect a source attribute to a target attribute.
5. Double-click the connecting mapping line to edit the transformation expression.
6. Review the generated JSONata expression and the sample preview.
7. Select Save.
8. Use Bulk edit transformations to test several expressions together and review their combined output.

Only attributes can be mapped. Entity and attribute names are case-sensitive, so use the spelling and capitalization shown in the source and target models.

## An example

Assume the source contains:

```json
{
    "students": [
        {
            "id": "1001",
            "status": "active",
            "name": {
                "first": " Avery ",
                "last": "Morgan"
            },
            "preferredName": "Ave",
            "email": " AVERY@EXAMPLE.EDU ",
            "emailType": "school"
        }
    ]
}
```

A basic expression that maps the source ID to Person.Identifier.identifier is:

```text
{
    "Person": [students.{
        "Identifier": [{
            "identifier": id
        }]
    }]
}
```

The result is:

```json
{
    "Person": [
        {
            "Identifier": [
                {
                    "identifier": "1001"
                }
            ]
        }
    ]
}
```

Read the expression from outside to inside:

- `{ ... }` creates an output object.
- `"Person":` creates the target property.
- `[ ... ]` guarantees that Person is an array, even when the source contains only one student.
- `students.{ ... }` evaluates the object after the dot once for each student.
- Inside that object, names such as `id` are relative to the current student.

## Common mapping patterns

### Copy a value

```text
{
    "Person": [students.{
        "Name": [{
            "firstName": name.first
        }]
    }]
}
```

Use a dot path such as `name.first` to navigate through nested source objects.

### Create nested LIF entities

The target structure must include every parent between the LIF root entity and the target attribute:

```text
{
    "Person": [students.{
        "Contact": [{
            "Email": [{
                "emailAddress": [email]
            }]
        }]
    }]
}
```

The brackets match fields defined as arrays in the target model. Always check the target model in the MDR to ensure the fields exist.

### Clean or format text

```text
{
    "Person": [students.{
        "Name": [{
            "firstName": $trim(name.first),
            "lastName": $uppercase(name.last)
        }],
        "Contact": [{
            "Email": [{
                "emailAddress": [$lowercase($trim(email))]
            }]
        }]
    }]
}
```

These string tools cover the most common cleanup and formatting needs:

| Tool | What it does | How it works |
|---|---|---|
| `$trim(string)` | Cleans whitespace. | Removes whitespace from both ends, changes tabs and line breaks to spaces, and collapses repeated spaces into one. |
| `$uppercase(string)` | Standardizes text as uppercase. | Returns a new string with every letter converted to uppercase. It does not change the source value. |
| `$lowercase(string)` | Standardizes text as lowercase. | Returns a new string with every letter converted to lowercase. This is useful before comparisons because string comparisons are case-sensitive. |
| `$substring(string, start, length)` | Extracts part of a string. | Starts at a zero-based character position and returns the remaining text or the optional number of characters. A negative start counts backward from the end. |
| `$split(string, separator, limit)` | Breaks one string into an array of strings. | Divides the text wherever it finds the separator, which can be text or a regular expression. The optional limit caps the number of returned parts. |
| `$join(array, separator)` | Combines an array of strings into one string. | Places the optional separator between the array items. Every item in the input array must be a string. |
| `$replace(string, pattern, replacement, limit)` | Finds and replaces text. | The pattern can be literal text or a regular expression. The optional limit controls how many replacements are made. |
| `value1 & value2` | Concatenates values into one string. | Joins the values on either side of `&`. JSONata converts non-string values to strings during concatenation. Add literal spaces or punctuation where the joined text needs them. |

For example:

```text
$trim(name.first) & " " & $trim(name.last)
```

### Add a condition

JSONata uses `condition ? value-if-true : value-if-false`:

```text
emailType = "school" ? "School" : "Personal"
```

Use `=` for equality and `!=` for inequality. Combine tests with `and` or `or`.

To include only active students:

```text
students[status = "active"]
```

Applied to a LIF fragment:

```text
{
    "Person": [students[status = "active"].{
        "Identifier": [{
            "identifier": id
        }]
    }]
}
```

### Supply a fallback

Use `$exists()` when a source value may be missing:

```text
$exists(preferredName) ? preferredName : name.first
```

This checks for presence rather than truthiness, so valid values such as `false`, `0`, or an empty string are not mistaken for missing data.

### Convert a type

```text
$number(credits)
$string(studentNumber)
$boolean(activeFlag)
```

Type conversion is important because a string such as `"3"` does not satisfy a target field that requires a number.

### Map a nested array

Given a courses array within each student:

```text
{
    "Person": [students.{
        "CourseLearningExperience": [courses.{
            "Course": [{
                "identifier": code,
                "name": title
            }]
        }]
    }]
}
```

The dot operator maps the expression on its right across the array on its left. Explicit brackets around the result preserve the target as an array when there is only one item.

### Reuse a calculated value

Use a parenthesized block and `:=` to define a local variable. Separate statements with semicolons; the last statement is returned.

```text
(
    $cleanEmail := $lowercase($trim(email));
    {
        "emailAddress": [$cleanEmail],
        "primaryEmailAddressIndicator": emailType = "school"
    }
)
```

Local variables begin with `$` and exist only within their surrounding block.

## A complete example

This example filters inactive students, cleans values, applies a fallback, and creates the expected LIF arrays:

```text
{
    "Person": [students[status = "active"].{
        "Identifier": [{
            "identifier": id,
            "identifierType": "SCHOOL_ASSIGNED_NUMBER"
        }],
        "Name": [{
            "firstName": $exists(preferredName) ? preferredName : $trim(name.first),
            "lastName": name.last
        }],
        "Contact": [{
            "Email": [{
                "emailAddress": [$lowercase($trim(email))],
                "emailAddressType": [emailType = "school" ? "School" : "Personal"]
            }]
        }]
    }]
}
```

Use this as a learning example, not as a substitute for checking your target model. Attribute types, array settings, and allowed values can differ across LIF model versions or organization extensions.

## How multiple MDR transformations combine

An MDR mapping group normally contains one transformation per target attribute. Each transformation should return an object-shaped fragment such as:

```text
{ "Person": [students.{ "Name": [{ "firstName": name.first }] }] }
```

The Translator combines the fragments as follows:

- Objects are merged recursively.
- Arrays of objects are merged item by item, by position.
- Arrays of primitive values are combined without duplicate values.
- A later scalar value replaces an earlier value at the same path.
- A result that is not an object, including a bare string, number, array, or null, is ignored by the runtime Translator.
- A fragment that violates the target schema is discarded.

Because arrays of objects merge by position, two expressions should produce records in the same order when they populate different attributes of the same target array. When that alignment is uncertain, create the related fields together in one expression and verify the combined output with realistic sample data.

## Test before you save

In the expression editor:

1. Select paths under Input schema instead of retyping long source paths.
2. Use the function list to insert common functions.
3. Review the generated sample input and preview the result.
4. Correct every expression error before saving.

Then open bulk edit transformations:

1. Prefer uploaded, realistic source JSON for final testing; generated data proves syntax but may not expose real nulls, empty arrays, unexpected codes, or one-item-array behavior.
2. Review both each transformation and the combined output.
3. Test zero, one, and multiple source records.
4. Confirm that all output property names and their capitalization match the target model.
5. Confirm that each target array remains an array containing only one source item.
6. Confirm that output values have the correct JSON type.

## Troubleshooting

| Symptom | Likely cause | What to check |
|---|---|---|
| Path returns no value | Incorrect path or capitalization | Compare the expression with Input schema; JSON paths are case-sensitive. |
| Preview shows an object where an array is expected | A one-item sequence collapsed to a single value | Wrap the mapped result in explicit brackets, for example `[students.{ ... }]`. |
| Expression works alone but disappears from combined output | It returned a scalar/array, or the fragment failed target validation | Return a complete object fragment and compare it with the target model. |
| A number or Boolean fails validation | The source supplied a string | Use `$number()` or `$boolean()` and retest. |
| Fields from separate expressions merge into the wrong array item | The source arrays have different ordering or lengths | Build related target array fields in one expression, or normalize ordering first. |
| A missing value produces an unwanted default | A truthiness fallback treated `0`, `false`, or `""` as absent | Use `$exists(value) ? value : fallback`. |
| Equality test behaves unexpectedly | A JavaScript-style operator was used | JSONata equality is `=`, not `==` or `===`. |
| A path with spaces or punctuation fails | The property name needs JSONata name escaping | Use backticks, for example ``record.`student-id` ``, or select the path from Input schema. |

## Quick reference

| Need | JSONata pattern |
|---|---|
| Read a nested value | `student.name.first` |
| Map every array item | `students.{ "id": id }` |
| Filter an array | `students[status = "active"]` |
| Force an array | `[students.{ ... }]` |
| Build an object | `{ "targetName": sourceName }` |
| Concatenate strings | `first & " " & last` |
| Check equality | `status = "active"` |
| Choose a value | `condition ? value1 : value2` |
| Check whether a value exists | `$exists(path)` |
| Define a local variable | `($x := expression; $x)` |
| Use the current item | `$` |
| Return to the input root | `$$` |

## Before publishing a mapping group

- The source and target models are correct.
- Every transformation returns an object-shaped target fragment.
- Source and target names match their models exactly, including capitalization.
- Objects and arrays match the target schema.
- Values have the correct types and allowed codes.
- Missing and optional source values are handled intentionally.
- Zero, one, and multiple records have been tested.
- Related array fragments merge correctly in the combined preview.
- Realistic source data produces the expected LIF output.

## Additional Resources

- [JSONata overview](https://docs.jsonata.org/overview)
- [Path operators](https://docs.jsonata.org/path-operators)
- [Building result structures](https://docs.jsonata.org/construction)
- [String, numeric, and other expressions](https://docs.jsonata.org/expressions)
- [Programming constructs, conditions, and variables](https://docs.jsonata.org/programming)
- [JSONata string functions](https://docs.jsonata.org/string-functions)
- [JSONata higher-order functions](https://docs.jsonata.org/higher-order-functions)
