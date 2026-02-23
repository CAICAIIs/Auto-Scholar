"""LLM prompt templates for workflow nodes.

Centralizes all prompts for easier maintenance and A/B testing.
Each template uses f-string formatting with named placeholders.
"""

KEYWORD_GENERATION_SYSTEM = """\
Generate 3-5 English search keywords for academic paper search.

Requirements:
- Each keyword: 2-4 words, specific enough to filter results
- Cover different angles: core concept, methodology, application domain
- Avoid overly broad single words (e.g. 'learning', 'analysis', 'model')\
"""

PLANNER_COT_SYSTEM = """\
You are a research planning agent. Analyze the user's research query and \
create a structured research plan using chain-of-thought reasoning.

STEP 1 - Analyze the query:
- Identify the core research topic and its sub-domains
- Determine if the query spans multiple aspects (e.g. methodology, application, theory)

STEP 2 - Decompose into sub-questions:
- Break the query into 2-5 focused sub-questions
- Each sub-question should be independently searchable
- Sub-questions should be mutually exclusive and collectively exhaustive

STEP 3 - For each sub-question, detine:
- 2-4 specific search keywords (English, 2-4 words each)
- The best data source: "semantic_scholar" for CS/AI, "pubmed" for biomedical, \
"arxiv" for recent preprints
- Estimated number of papers needed (3-15)
- Priority (1 = highest, 5 = lowest)

STEP 4 - Write your reasoning:
- Explain WHY you decomposed this way
- Justify your source recommendations

Output your reasoning in the "reasoning" field and sub-questions in "sub_questions".\
"""

KEYWORD_GENERATION_CONTINUATION = """\


This is a follow-up request. Consider the conversation history \
when generating keywords to find additional relevant papers.
Conversation history:
{conversation_context}\
"""

CONTRIBUTION_EXTRACTION_SYSTEM = """\
Extract the paper's core contribution in ONE sentence (15-30 words).
Format: "[Novel method/key finding] that [achieves/enables] [specific outcome]"
If abstract is vague, infer from title. Output in English.
CRITICAL: You MUST return a non-empty string for core_contribution.\
"""

STRUCTURED_EXTRACTION_SYSTEM = """\
Extract structured information from the paper in 8 dimensions.
Each field should be 1-2 sentences. Use null if information is not available.

DIMENSIONS:
1. problem: What research problem is being addressed?
2. method: What methodology or approach is used?
3. novelty: What are the key innovations or contributions?
4. dataset: What datasets are used? (null for theoretical papers)
5. baseline: What baseline methods are compared? (null if no comparison)
6. results: What are the key experimental results or findings?
7. limitations: What limitations are acknowledged? (null if not mentioned)
8. future_work: What future directions are suggested? (null if not mentioned)

RULES:
- Extract ONLY information explicitly stated or strongly implied in the abstract
- Use null for fields where information is genuinely unavailable
- Keep each field concise (1-2 sentences max)
- Output in English regardless of input language\
"""

STRUCTURED_EXTRACTION_USER = """\
Title: {title}
Year: {year}
Abstract: {abstract}\
"""

CONTRIBUTION_EXTRACTION_USER = """\
Title: {title}
Year: {year}
Abstract: {abstract}\
"""

DRAFT_GENERATION_SYSTEM = """\
Write a structured literature review with 4-6 thematic sections \
in formal academic {language_name}.

REQUIRED SECTIONS:
1. Introduction/Background - overview of the research area
2-4. Thematic sections - group papers by methodology, approach, or application
5. Methodology Comparison - compare and contrast the methods used across papers \
(include a comparison of strengths, limitations, datasets, and key findings)
6. Conclusion/Future Directions - summarize insights and identify research gaps

CITATION RULES:
- Use {{cite:N}} to reference papers, where N is the number shown \
in brackets in the paper list (1 to {num_papers}).
- Example: "Smith et al. {{cite:1}} proposed X, while Jones {{cite:3}} extended Y."
- You MUST cite ALL {num_papers} papers. Do NOT invent numbers outside 1-{num_papers}.\
"""

DRAFT_REVISION_ADDENDUM = """\


This is a REVISION request. The user wants to modify the existing draft.{existing_draft_summary}
User's modification request: {user_query}

Conversation history:
{conversation_context}

Please revise the draft according to the user's request while maintaining \
proper citations and academic quality.\
"""

DRAFT_RETRY_ADDENDUM = """\


PREVIOUS ATTEMPT FAILED ({error_count} errors). Fix these:
{error_list}
REMINDER: Valid citation numbers are 1 to {num_papers}. \
Use ONLY {{cite:1}} through {{cite:{num_papers}}}. \
Every paper (1-{num_papers}) MUST be cited at least once.\
"""

DRAFT_USER_PROMPT = """\
Research Topic: {user_query}

Papers for Review:
{paper_context}\
"""

OUTLINE_GENERATION_SYSTEM = """\
Create an outline for a literature review on the given topic.

Generate a title and 4-6 section titles that will structure the review.

REQUIRED STRUCTURE:
1. Introduction/Background
2-4. Thematic sections (group by methodology, approach, or application)
5. Methodology Comparison
6. Conclusion/Future Directions

Output section titles in {language_name}. Be specific to the research topic.\
"""

SECTION_GENERATION_SYSTEM = """\
Write the "{section_title}" section of a literature review in {language_name}.

CONTEXT:
- This is section {section_num} of {total_sections}
- Full outline: {outline_titles}

CITATION RULES:
- Use {{cite:N}} to reference papers (N = 1 to {num_papers})
- Cite relevant papers from the list below
- Do NOT invent citation numbers outside 1-{num_papers}

Write 2-4 paragraphs with proper academic tone and citations.\
"""

CLAIM_EXTRACTION_SYSTEM = """\
Extract atomic claims from the given text. Each claim should be:
- A single factual statement that can be independently verified
- Contains at least one citation reference {{cite:N}}
- Self-contained (understandable without surrounding context)

Split compound sentences into separate claims when they make distinct assertions.
Preserve the exact citation markers {{cite:N}} from the original text.
Output claims in the same language as the input text.\
"""

CLAIM_EXTRACTION_USER = """\
Section: {section_title}
Text:
{section_content}\
"""

CLAIM_VERIFICATION_SYSTEM = """\
Determine if the cited paper's content supports the given claim.

LABELS:
- entails: The paper content directly supports or implies the claim
- insufficient: The paper content is related but doesn't provide enough evidence
- contradicts: The paper content contradicts or refutes the claim

Be strict: only mark "entails" if the evidence clearly supports the claim.
If the claim makes a stronger assertion than the evidence supports, mark "insufficient".\
"""

CLAIM_VERIFICATION_USER = """\
CLAIM: {claim_text}

CITED PAPER [{citation_index}]:
Title: {paper_title}
Abstract: {paper_abstract}
Core Contribution: {paper_contribution}\
"""

REFLECTION_SYSTEM = """\
You are a quality assurance reflection agent for academic literature reviews.

Analyze the QA errors from the critic and produce a structured reflection.

ERROR CATEGORIES:
- citation_out_of_bounds: A {{cite:N}} reference where N exceeds the valid paper range
- missing_citation: A section contains no citations at all
- uncited_paper: An approved paper was never cited in the review
- low_entailment: A claim's cited paper does not sufficiently support the statement
- structural: Other structural issues (empty sections, formatting problems)

For each error:
1. Classify it into exactly one category
2. Write a specific fix strategy the writer can follow
3. Determine if the writer alone can fix it (True) or if re-retrieval is needed (False)

ROUTING RULES:
- If ALL errors are fixable_by_writer=True → retry_target="writer_agent"
- If ANY error requires re-retrieval (e.g. not enough papers to cite) → retry_target="retriever_agent"
- If errors are trivial or unlikely to improve on retry → should_retry=False

Be concise. Focus on actionable fix strategies, not explanations.\
"""

REFLECTION_USER = """\
Number of approved papers: {num_papers}
Valid citation range: 1 to {num_papers}
Retry attempt: {retry_count}

QA Errors:
{error_list}\
"""

DRAFT_REFLECTION_RETRY_ADDENDUM = """\


PREVIOUS ATTEMPT FAILED. A reflection agent analyzed the errors and produced \
targeted fix strategies. Follow them precisely:

{reflection_instructions}

REMINDER: Valid citation numbers are 1 to {num_papers}. \
Use ONLY {{cite:1}} through {{cite:{num_papers}}}. \
Every paper (1-{num_papers}) MUST be cited at least once.\
"""
