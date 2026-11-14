# Comparisons, prototypes and real-player A/B tests

## Choose the kind of evidence

A controlled agent replay checks a mechanic, a regression or a visible outcome.
A design comparison can reveal trade-offs. Neither measures human engagement.
A human playtest explores real behaviour; a randomised A/B experiment can test
a defined effect in an appropriate player population. Do not call repeated agent
sessions an A/B engagement study or infer retention from task speed alone.

## Write the question before the variant

For each proposal record:

1. Observed moment and source evidence; interpretation separately.
2. Hypothesis, intended audience and the result that would contradict it.
3. Control and treatment. Change one meaningful factor for a causal question;
   if testing a bundle, explicitly admit that attribution is limited.
4. Reset/checkpoint, build, seed and task for a local comparison. Control order
   and learning effects where relevant. Keep failed variants and restoration evidence.
5. Primary outcome and guardrails. For example, understanding a tool plus time
   to a first intentional mark; guard against mistakes, frustration and lost
   creative freedom. Faster completion is not necessarily more enjoyable.
6. Status: proposed, simulated, agent-executed or human-executed. Record missing
   evidence, sample limitations and the next decision. Never upgrade a mock-up
   to a successful experiment.

For imaginative features, a prototype or qualitative playtest may be more useful
than immediately running A/B tests. Use the cheapest evidence that answers the
question without claiming more than it can show.

## Before a real-player experiment

Obtain separate approval for code changes, instrumentation, data handling and
recruitment. Define consent and privacy requirements, especially for children.
Do not enrol players, enable analytics or ship a variant from this skill alone.

Predefine the eligible population, random assignment unit, exposure window,
primary outcome, meaningful effect, uncertainty approach and stopping rule with
an appropriate researcher/statistician. Choose sample size from those inputs,
not a universal number. Avoid repeated significance peeking, post-hoc outcome
switches and selective reporting. Document learning effects, novelty, carry-over,
multiple comparisons and attrition where they matter.

Measure player value, not just session length or ad exposure. Include task
success, comprehension, satisfaction or voluntary return when appropriate, and
guardrails for crashes, accessibility, frustration, accidental purchases and
privacy. Keep identifiers out of reports. A result only applies within the
tested context; negative and inconclusive results are useful too.

Never promise a feature will improve retention from an agent's visual judgement.
Present the evidence, uncertainty and the choice the developer can make next.
