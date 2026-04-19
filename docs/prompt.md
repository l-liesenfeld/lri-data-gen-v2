# How the prompt is built

The prompt is the single most important piece of IP in this system. This page describes how it's assembled; the authoritative source is [`prompts/legacy.txt`](../prompts/legacy.txt) plus constants in [`src/prompt_builder.py`](../src/prompt_builder.py). Change the template there, not the description here.

## Big-picture shape

Each call sends two messages:

1. **System** — a fixed role-framing sentence (constant `SYSTEM_MESSAGE` in `prompt_builder.py`):
   > "You are an expert in psychological text generation, skilled at creating realistic human-like journal entries that subtly incorporate specific psychological motives and patterns. You understand how underlying psychological drives manifest in writing without being explicitly stated."

2. **User** — a markdown document with 8 fixed sections, filled in from the experiment config.

All calls in a run share the same prompt (identical context). Variation across responses comes from temperature + model sampling, not from prompt mutation.

## The 8 user-message sections (in order)

1. **OBJECTIVE** — states the purpose: generate a realistic journal entry for training data.
2. **BACKGROUND** — role frame: simulating a psychotherapy client writing in a weekly journal.
3. **PSYCHOLOGICAL MOTIVES TO EMBED** — the motives selected for this experiment, one per line.
4. **HOW TO EMBED MOTIVES** — the embedding-channel taxonomy. **This is the single most important block** and is identical across every run.
5. **LANGUAGE INSTRUCTIONS** — English-only, Deutsch-only, or bilingual instructions, chosen by `generation.language`.
6. **DEMOGRAPHIC & SITUATIONAL CONTEXT** — defaults to "Vary demographics naturally / Vary life situations"; if `context_hint` is set it appends an "Additional context: …" line.
7. **RESPONSE FORMAT** — target length + a literal JSON template showing the expected output shape.
8. **IMPORTANT GUIDELINES** — 6 final rules: be realistic, don't name motives, include cognitive inconsistencies, hesitations, varied style, not clinical.

## Motive injection

Each selected motive becomes one bullet in section 3:

```
- Persönliche Begegnung (ID: A1): (freudig-intuitiver Austausch: intimacy) persönlich werden, sich (auch in der Tiefe) verstehen, ... Strength: 0.7 out of 1.0
```

Name and description are pulled from `data/motive_matrix.json`. The strength number is embedded verbatim; the model interprets the scale using the rules in section 4.

## Strength

There is **no scaling adjective** or conditional block for strength. The model sees the raw number plus this rule:

> Higher strength values (closer to 1.0) mean the motive should be more detectable (though still not explicitly stated). Lower values (closer to 0.0) mean the motive should be more deeply hidden and nuanced or even ambiguous.

Strength is also echoed in the inline JSON template (section 7) so it ends up in the model's `motives_present` ground truth labels.

## Response format enforcement

Two mechanisms combined:

- **`response_format: {"type": "json_object"}`** in the OpenAI API call, so the completion is guaranteed to parse as JSON.
- **An inline JSON template** inside the prompt showing a single `responses[0]` entry with `motives_present` pre-filled. The pre-fill is the ground-truth echo — labels can't be hallucinated because they're already in the skeleton.

The template shape is:

```json
{
  "responses": [
    {
      "response_id": 1,
      "text": "[TEXT WILL BE GENERATED HERE IN ENGLISH]",
      "motives_present": [
        {"id": "A1", "name": "Persönliche Begegnung", "strength": 0.7}
      ]
    }
  ]
}
```

In bilingual mode an extra `text_deutsch` field is added alongside `text`.

## Language

The prompt itself is always English. Only the *generated text* is in the target language. This keeps the instructional scaffolding stable — the model only swaps output language, not prompt language.

Per-language strings live in `LANGUAGE_FRAGMENTS` in `prompt_builder.py`:

| Language | `prompt_instructions` | Adds `text_deutsch`? |
|---|---|---|
| `english` | "All journal entry text should be written in English." | No |
| `deutsch` | "All journal entry text should be written in German (Deutsch)." | No |
| `deutsch-english` | "Provide both the English version and a German translation." | Yes |

## Context hint

Optional free text. If set, appended as:

```
Additional context: workplace situation
```

There are two unused parameters (`demographicDetails`, `situation`) carried over from the old tool. They're not surfaced anywhere in phase 1 and can be removed or wired in phase 2.

## Techniques used

- **Role framing** in the system message and section 2.
- **Negative instructions** in section 8 ("DO NOT explicitly name the motives").
- **Explicit embedding-channel taxonomy** in section 4: word choice, sentence structure, topics of concern, emotional tone, attribution patterns, defense mechanisms. Gives the model concrete levers beyond "be subtle".
- **Shape-by-example** via the JSON template, paired with the API-level JSON mode.
- **Ground-truth echo** — labels are pre-filled so they never drift.
- **Authenticity cues** — "cognitive inconsistencies", "hesitations", "self-corrections" push output away from stilted LLM prose.

## Why it works

1. Clear purpose (training data for a detection model) tells the model to be realistic, not clinical.
2. The embedding-channel taxonomy gives concrete realization levers.
3. The negative constraint prevents the common failure of naming the motive in-text.
4. Labels are echoed from the template, never hallucinated.
5. Explicit realism cues counter default LLM cadence.

## Changing it

Small edits: open `prompts/legacy.txt`, edit, save. No code changes needed. `python cli.py validate` won't catch prompt-content issues — run a small (n=5) experiment and eyeball the output.

Larger changes (new placeholders, new sections): update both the template and `src/prompt_builder.py:build_prompt` to inject the new fields.
