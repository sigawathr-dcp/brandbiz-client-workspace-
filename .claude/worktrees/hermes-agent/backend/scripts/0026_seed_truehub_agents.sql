-- Seed True AI Hub agent data into the agents table.
-- Raw SQL equivalent of backend/scripts/seed_agents.py, generated from
-- backend/scripts/seed_data/agents.json (source: True_AI_agent_data.md export).
-- Use this if you want to load the agents directly via psql instead of running
-- the Python seeder inside the backend-api container, e.g. against staging:
--   psql "$STAGING_DATABASE_URL" -f backend/scripts/0026_seed_truehub_agents.sql
--
-- Requires: agents/agent_files tables (migration 0018_agents) already applied
-- -- included in backend/scripts/0001_0025_staging_bootstrap.sql.
--
-- Idempotent: users are upserted by google_email (ON CONFLICT DO NOTHING);
-- agents are inserted only if no row with the same (user_id, name) exists yet
-- (matches the skip logic in seed_agents.py). Safe to re-run. A corrective
-- UPDATE at the end also repairs seeded agents left with stale provider/model
-- by an earlier version of this script, so re-running fixes existing rows too.
--
-- All agents are seeded with provider='local', model='gemma4:26b' — the
-- LOCAL_MODEL_CODE in app/llm/router.py — rather than the per-agent
-- provider/model values from the original export. Migration
-- 0024_agents_local_model reset all agents to the local model; seeding the
-- export values would reintroduce non-local providers on a fresh database.
--
-- Does not write agent_created audit_log rows (unlike the Python seeder, which
-- calls audit_svc.log per agent) -- this is a bulk historical data load, not a
-- live user action; PLAN.md Section 7.3 (append-only audit log) is not violated
-- by omitting synthetic entries for it.

BEGIN;

-- Seed users, keyed by True AI Hub author display name
INSERT INTO users (google_email, display_name, role, is_active, consent_acknowledged_at)
VALUES
    ('core-admin@truehub.seed', 'Core Admin', 'ADMIN'::role_level, TRUE, now()),
    ('test-core-admin@truehub.seed', 'test_core_admin', 'ADMIN'::role_level, TRUE, now()),
    ('sikwat-r@truehub.seed', 'ศิกวัฒฐ รุ่งเรือง', 'ADMIN'::role_level, TRUE, now())
ON CONFLICT (google_email) DO NOTHING;

-- 119 agents
INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sale) Strategic Account Planner$ag$, 'local', 'gemma4:26b', $ag$Generate strategic account plan$ag$, $ag$You are an expert in Create an account plan for [customer name]. Use these inputs: company profile, known priorities, current product usage, stakeholders, and renewal date. Output a structured plan with goals, risks, opportunities, and next steps.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'test-core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sale) Strategic Account Planner$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sale) Competitive Positioning Analysis$ag$, 'local', 'gemma4:26b', $ag$Competitive positioning analysis$ag$, $ag$I'm preparing a competitive battlecard for [competitor name].
Research their pricing model, product positioning, recent customer wins/losses, and sales motion.
Adapt the research scope and depth to match this competitor's business model, target customers, and industry context.
Compare it to ours based on these strengths: [insert].
Output a one-page summary with citations.$ag$, '{"web_search": true, "think_longer": true, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'test-core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sale) Competitive Positioning Analysis$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Engineer) Write JIRA ticket from spec$ag$, 'local', 'gemma4:26b', $ag$Write JIRA ticket from spec$ag$, $ag$You are an expert in draftig a JIRA ticket that includes the problem statement, context, goals, acceptance criteria, and technical notes for implementation.Based on this engineering spec for [insert task or feature]$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Engineer$ag$
FROM users u WHERE u.google_email = 'test-core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Engineer) Write JIRA ticket from spec$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(General) Rewrite for clarity$ag$, 'local', 'gemma4:26b', $ag$Rewrite for clarity$ag$, $ag$You are an expert in: Rewrite the following text so it is easier to understand. The text will be used in a professional setting. Ensure the tone is clear, respectful, and concise. Text: [paste text]$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$General$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(General) Rewrite for clarity$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(General) Draft meeting invite$ag$, 'local', 'gemma4:26b', $ag$Draft meeting invite$ag$, $ag$You are an expert in: Draft a meeting invitation for a session about [topic]. The meeting will include [attendees/roles] and should outline agenda items, goals, and preparation required. Provide the text in calendar-invite format.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$General$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(General) Draft meeting invite$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(General) Summarize long email$ag$, 'local', 'gemma4:26b', $ag$Summarize long email$ag$, $ag$You are an expert in: Summarize this email thread into a short recap. The thread includes several back-and-forth messages. Highlight key decisions, action items, and open questions. Email: [paste text].$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$General$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(General) Summarize long email$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(General) Create an action items list$ag$, 'local', 'gemma4:26b', $ag$Create an action items list$ag$, $ag$You are an expert in: Turn the following meeting notes into a clean task list. The tasks should be grouped by owner and include deadlines if mentioned. Notes: [paste text].$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$General$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(General) Create an action items list$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(General) Prep questions for a meeting$ag$, 'local', 'gemma4:26b', $ag$Prep questions for a meeting$ag$, $ag$You are an expert in: Suggest thoughtful questions to ask in a meeting about [topic]. The purpose of the meeting is [purpose]. Provide a list of at least 5 questions that show preparation and insight.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$General$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(General) Prep questions for a meeting$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Brainstorm campaign ideas$ag$, 'local', 'gemma4:26b', $ag$Brainstorm campaign ideas$ag$, $ag$You are an expert in: Brainstorm 5 creative campaign ideas for our upcoming [event/launch]. The audience is [insert target], and our goal is [insert goal]. Include a theme, tagline, and 1-2 core tactics per idea.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Brainstorm campaign ideas$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Research emerging trends in buyer behavior$ag$, 'local', 'gemma4:26b', $ag$Research emerging trends in buyer behavior$ag$, $ag$You are an expert in: Research 2024 trends in how [type] buyers research and evaluate [industry] products. Include behavior shifts, content preferences, and channel usage. Cite sources and format as a short briefing with bullet-point insights.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Research emerging trends in buyer behavior$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Research regional campaign benchmarks$ag$, 'local', 'gemma4:26b', $ag$Research regional campaign benchmarks$ag$, $ag$You are an expert in: Research typical CTRs, CPCs, and conversion rates for digital campaigns targeting [location] in 2024. Focus on [ad channels]. Include source links and a table comparing each metric by country.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Research regional campaign benchmarks$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Create a social post series$ag$, 'local', 'gemma4:26b', $ag$Create a social post series$ag$, $ag$You are an expert in: Draft a 3-post social media series promoting [event, product, or milestone]. Use this background for context: [paste details]. Each post should include copy and a suggested visual description.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Create a social post series$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Create a customer spotlight post$ag$, 'local', 'gemma4:26b', $ag$Create a customer spotlight post$ag$, $ag$You are an expert in: Write a customer spotlight post based on this success story: [paste key details]. Make it conversational, authentic, and aligned to our brand voice. Output as a LinkedIn post draft.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Create a customer spotlight post$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Rework demo follow-up email$ag$, 'local', 'gemma4:26b', $ag$Rework demo follow-up email$ag$, $ag$You are an expert in: Rewrite this follow-up email after a demo to sound more consultative. Original email: [paste here]. Include recap, next steps, and call scheduling CTA. Output as email text.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Rework demo follow-up email$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Create summary of rep activity$ag$, 'local', 'gemma4:26b', $ag$Create summary of rep activity$ag$, $ag$You are an expert in: Write a daily update summarizing key rep activities. Inputs: [paste call summaries or CRM exports]. Make it upbeat and concise. Output as 3–5 bullet message.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Create summary of rep activity$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Regional market entry planning$ag$, 'local', 'gemma4:26b', $ag$Regional market entry planning$ag$, $ag$You are an expert in: I'm evaluating market entry into [region/country] for our [SaaS solution]. Research local buying behaviors, competitive landscape, economic conditions, and regulatory concerns. Format as a go/no-go market readiness summary with citations and action steps.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Regional market entry planning$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Prepare sales objection rebuttals$ag$, 'local', 'gemma4:26b', $ag$Prepare sales objection rebuttals$ag$, $ag$You are an expert in: Create rebuttals to these common objections: [insert 2–3 objections]. Make them sound natural and confident, and include a backup stat or story where useful. Output as list.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Prepare sales objection rebuttals$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Summarize campaign attribution to closed deals$ag$, 'local', 'gemma4:26b', $ag$Summarize campaign attribution to closed deals$ag$, $ag$You are an expert in: Match campaign sources to closed-won deals from this data. Identify which campaign drove the most closed revenue. Data: [Upload campaign + deal export]. Output a ranked list and a short campaign summary.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Summarize campaign attribution to closed deals$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Executive) Exec update talking points$ag$, 'local', 'gemma4:26b', $ag$Exec update talking points$ag$, $ag$You are an expert in: I need to brief my VP on team progress. Based on this weekly summary: [insert notes], generate concise talking points grouped into achievements, blockers, and asks.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Executive$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Executive) Exec update talking points$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Executive) Improve feedback delivery$ag$, 'local', 'gemma4:26b', $ag$Improve feedback delivery$ag$, $ag$You are an expert in: I want to give constructive feedback to a report who is underperforming. The issue is [insert behavior]. Suggest 2-3 ways to phrase it constructively, with pros and cons of each approach.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Executive$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Executive) Improve feedback delivery$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Executive) Hybrid engagement best practices$ag$, 'local', 'gemma4:26b', $ag$Hybrid engagement best practices$ag$, $ag$You are an expert in: I lead a hybrid team in [insert industry]. Research effective engagement and collaboration practices from the last 2 years. Focus on techniques proven to improve team trust, reduce burnout, and sustain productivity. Provide a top 5 list with supporting evidence and links.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Executive$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Executive) Hybrid engagement best practices$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Executive) Compare DEI strategy examples$ag$, 'local', 'gemma4:26b', $ag$Compare DEI strategy examples$ag$, $ag$You are an expert in: I'm helping shape our team's DEI goals. Research how leading companies in [insert industry] structure their DEI initiatives at the team level. Include examples of KPIs, training, and rituals. Return a comparison table with links.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Executive$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Executive) Compare DEI strategy examples$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Executive) Understand burnout risks and mitigation$ag$, 'local', 'gemma4:26b', $ag$Understand burnout risks and mitigation$ag$, $ag$You are an expert in: I'm seeing signs of burnout on my team. Research recent studies or expert guidance on recognizing burnout in knowledge workers and preventing escalation. Summarize key risk factors and recommend a 3-part action plan with citations.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Executive$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Executive) Understand burnout risks and mitigation$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Draft a vision statement for the product$ag$, 'local', 'gemma4:26b', $ag$Draft a vision statement for the product$ag$, $ag$You are an expert in: Based on this long-term goal and user need, write a concise product vision statement. Keep it inspiring and grounded in real outcomes. [Insert product goal]$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Draft a vision statement for the product$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Create a go-to-market FAQ$ag$, 'local', 'gemma4:26b', $ag$Create a go-to-market FAQ$ag$, $ag$You are an expert in: Draft an internal FAQ for our sales and support teams about our upcoming feature launch. Use this background and anticipated questions. Write in a confident, informative tone. [Insert feature and launch details]$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Create a go-to-market FAQ$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Brainstorm feature ideas from customer feedback$ag$, 'local', 'gemma4:26b', $ag$Brainstorm feature ideas from customer feedback$ag$, $ag$Review this batch of customer feedback from the past quarter. Identify pain points and generate a list of 5 feature ideas to address recurring themes. [Insert feedback or summary]$ag$, '{"web_search": true, "think_longer": true, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'test-core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Brainstorm feature ideas from customer feedback$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(General) Adapt message for audience$ag$, 'local', 'gemma4:26b', $ag$Adapt message for audience$ag$, $ag$You are an expert in: Reframe this message for [audience type: executives, peers, or customers]. The message was originally written for [context]. Adjust tone, word choice, and style to fit the intended audience. Text: [paste text].$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$General$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(General) Adapt message for audience$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(General) Create a meeting agenda$ag$, 'local', 'gemma4:26b', $ag$Create a meeting agenda$ag$, $ag$You are an expert in: Create a structured agenda for a meeting about [topic]. The meeting will last [time] and include [attendees]. Break the agenda into sections with time estimates and goals for each section.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$General$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(General) Create a meeting agenda$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(General) Summarize meeting notes$ag$, 'local', 'gemma4:26b', $ag$Summarize meeting notes$ag$, $ag$You are an expert in: Summarize these meeting notes into a structured recap. The notes are rough and informal. Organize them into categories: key decisions, next steps, and responsibilities. Notes: [paste text].$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$General$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(General) Summarize meeting notes$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(General) Draft follow-up email$ag$, 'local', 'gemma4:26b', $ag$Draft follow-up email$ag$, $ag$You are an expert in: Write a professional follow-up email after a meeting about [topic]. Include a recap of key points, assigned responsibilities, and next steps with deadlines. Use a clear and polite tone.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$General$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(General) Draft follow-up email$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(General) Summarize a long document$ag$, 'local', 'gemma4:26b', $ag$Summarize a long document$ag$, $ag$You are an expert in: Summarize the following document into 5 key points and 3 recommended actions. The document is [type: report, plan, or notes]. Keep the summary concise and professional. Text: [paste document].$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$General$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(General) Summarize a long document$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(General) Brainstorm solutions$ag$, 'local', 'gemma4:26b', $ag$Brainstorm solutions$ag$, $ag$You are an expert in: Brainstorm potential solutions to the following workplace challenge: [describe challenge]. Provide at least 5 varied ideas, noting pros and cons for each.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$General$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(General) Brainstorm solutions$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Visualize campaign timeline$ag$, 'local', 'gemma4:26b', $ag$Visualize campaign timeline$ag$, $ag$You are an expert in: Build a timeline for our upcoming multi-channel campaign. Key dates and milestones are: [insert info]. Output as a horizontal timeline with phases, owners, and deadlines.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Visualize campaign timeline$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Draft a creative brief$ag$, 'local', 'gemma4:26b', $ag$Draft a creative brief$ag$, $ag$You are an expert in: Create a creative brief for our next paid media campaign. Here's the goal, audience, and offer: [insert info]. Include sections for objective, audience insights, tone, assets needed, and KPIs.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Draft a creative brief$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Research AI tools for marketers$ag$, 'local', 'gemma4:26b', $ag$Research AI tools for marketers$ag$, $ag$You are an expert in: Research the most recommended [tools] for marketers by function (e.g. copywriting, planning, analytics, design). Create a table with features, pricing, pros/cons, and primary use case. Include sources.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Research AI tools for marketers$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Generate ad copy variations$ag$, 'local', 'gemma4:26b', $ag$Generate ad copy variations$ag$, $ag$You are an expert in: Create 5 ad copy variations for a [channel] campaign. Here's the campaign theme and audience info: [insert context]. Each version should test a different hook or tone.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Generate ad copy variations$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Develop a brand style guide outline$ag$, 'local', 'gemma4:26b', $ag$Develop a brand style guide outline$ag$, $ag$You are an expert in: Create an outline for a brand style guide for [company/product]. Include sections for typography, color palette, logo usage, tone of voice, imagery style, and do's/don'ts.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Develop a brand style guide outline$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Refresh brand identity concepts$ag$, 'local', 'gemma4:26b', $ag$Refresh brand identity concepts$ag$, $ag$You are an expert in: Suggest 3 creative directions to refresh our brand identity. Include possible color palettes, typography styles, visual motifs, and tone updates that align with [audience/market shift].$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Refresh brand identity concepts$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Draft exec update on pipeline status$ag$, 'local', 'gemma4:26b', $ag$Draft exec update on pipeline status$ag$, $ag$You are an expert in: Summarize our pipeline health this month for execs. Inputs: [paste data]. Include total pipeline, top risks, biggest wins, and forecast confidence. Write it like a short exec update.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Draft exec update on pipeline status$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Design territory planning framework$ag$, 'local', 'gemma4:26b', $ag$Design territory planning framework$ag$, $ag$You are an expert in: Create a territory planning guide for our next fiscal year. Inputs: team headcount, target industries, regions, and historical revenue. Recommend allocation method and sample coverage plan.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Design territory planning framework$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Create battlecard for competitor$ag$, 'local', 'gemma4:26b', $ag$Create battlecard for competitor$ag$, $ag$You are an expert in: Create a battlecard for [competitor name]. Use these notes: [insert positioning data]. Include strengths, weaknesses, how we win, and quick talk track. Output as table format.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Create battlecard for competitor$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Competitive positioning analysis$ag$, 'local', 'gemma4:26b', $ag$Competitive positioning analysis$ag$, $ag$You are an expert in: I'm preparing a competitive battlecard for [competitor name]. Research their pricing model, product positioning, recent customer wins/losses, and sales motion. Compare it to ours based on these strengths: [insert]. Output a 1-page summary with citations.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Competitive positioning analysis$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Analyze pipeline conversion rates by stage$ag$, 'local', 'gemma4:26b', $ag$Analyze pipeline conversion rates by stage$ag$, $ag$You are an expert in: Analyze this sales pipeline export. Calculate conversion rates between each stage and identify the biggest drop-off point. Data: [Upload pipeline CSV]. Output a short summary and a table of conversion % by stage.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Analyze pipeline conversion rates by stage$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Generate performance comparison chart$ag$, 'local', 'gemma4:26b', $ag$Generate performance comparison chart$ag$, $ag$You are an expert in: Here's a table of rep performance by quarter: [paste data]. Compare top vs bottom performers. Show chart with trends and call out key differences. Output as table + insights.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Generate performance comparison chart$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Executive) Run a skills gap analysis$ag$, 'local', 'gemma4:26b', $ag$Run a skills gap analysis$ag$, $ag$You are an expert in: I'm trying to assess skill gaps on my team. Here's our current skill matrix and desired future state: [insert info]. Identify key gaps and suggest training or hiring solutions. Return findings in a short table.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Executive$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Executive) Run a skills gap analysis$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Executive) Plan a hiring roadmap$ag$, 'local', 'gemma4:26b', $ag$Plan a hiring roadmap$ag$, $ag$You are an expert in: I need to plan hiring needs for the next two quarters. Here's our current team structure and projected growth: [insert info]. Suggest a phased hiring plan with rationale for each role and proposed timing.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Executive$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Executive) Plan a hiring roadmap$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Executive) Create a 1:1 template$ag$, 'local', 'gemma4:26b', $ag$Create a 1:1 template$ag$, $ag$You are an expert in: Draft a 1:1 meeting template for my direct reports. I want it to include check-ins on progress, roadblocks, career growth, and feedback. Format it as a bulleted agenda with guiding questions.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Executive$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Executive) Create a 1:1 template$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Executive) Prepare for a difficult conversation$ag$, 'local', 'gemma4:26b', $ag$Prepare for a difficult conversation$ag$, $ag$You are an expert in: I have a difficult conversation coming up with a team member about [insert issue]. Help me think through what to say, how to open, and what questions to ask. Return a 3-part conversation guide.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Executive$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Executive) Prepare for a difficult conversation$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Executive) Benchmark manager-to-IC ratios$ag$, 'local', 'gemma4:26b', $ag$Benchmark manager-to-IC ratios$ag$, $ag$You are an expert in: I'm a [insert role, e.g. Senior Engineering Manager] at a [insert company type, e.g., 500-person SaaS company]. I want to benchmark manager-to-IC ratios across similar tech firms. Focus on industry norms, variations by team type (engineering, product, etc.), and recommendations for scaling. Provide citations and a comparison table.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Executive$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Executive) Benchmark manager-to-IC ratios$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Executive) Research effective upskilling programs$ag$, 'local', 'gemma4:26b', $ag$Research effective upskilling programs$ag$, $ag$You are an expert in: I'm designing an upskilling program for a [insert team type, e.g., customer support team]. Find case studies or frameworks from companies that have implemented successful internal training programs. Include how they measured success, duration, and tools used. Summarize in 3–4 paragraphs with links.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Executive$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Executive) Research effective upskilling programs$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Benchmark competitor pricing strategies$ag$, 'local', 'gemma4:26b', $ag$Benchmark competitor pricing strategies$ag$, $ag$You are an expert in: I'm a product manager launching a new SaaS product. Research how top 5 competitors in this space structure their pricing tiers, freemium vs. paid, feature gating, and upsell triggers. Use public sources and include URLs. Output: A comparison table with insights and risks.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Benchmark competitor pricing strategies$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sale) Create a sales enablement one-pager$ag$, 'local', 'gemma4:26b', $ag$Create a sales enablement one-pager$ag$, $ag$Create a one-pager to help reps pitch [product name] to [persona]. Include key benefits, features, common use cases, and competitor differentiators. Format as copy-ready enablement doc. Refer to the websearch informatiin for missing info.$ag$, '{"web_search": true, "think_longer": true, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'test-core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sale) Create a sales enablement one-pager$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Draft PRD for a new feature$ag$, 'local', 'gemma4:26b', $ag$Draft PRD for a new feature$ag$, $ag$Based on this feature idea and customer need, write a first-draft PRD. Include user story, problem statement, solution overview, acceptance criteria, and success metrics. [Insert context or problem]$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'test-core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Draft PRD for a new feature$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(IT) Translate error logs to plain language$ag$, 'local', 'gemma4:26b', $ag$Translate error logs to plain language$ag$, $ag$Help translate these system error logs into language that can be understood by a non-technical executive. Use definitions where needed, and summarize what each log entry means in a few clear sentences. Present the explanation as an email draft.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$IT$ag$
FROM users u WHERE u.google_email = 'test-core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(IT) Translate error logs to plain language$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(General) Write a project update$ag$, 'local', 'gemma4:26b', $ag$Write a project update$ag$, $ag$You are an expert in: Draft a short project update for stakeholders. The project is [describe project]. Include progress made, current blockers, and next steps. Write in a professional, concise style.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$General$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(General) Write a project update$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Build a customer journey map$ag$, 'local', 'gemma4:26b', $ag$Build a customer journey map$ag$, $ag$You are an expert in: Create a customer journey map for our [product/service]. Our typical customer is [insert profile]. Break it into stages, goals, touchpoints, and potential pain points per stage. Output as a table.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Build a customer journey map$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Research industry event competitor presence$ag$, 'local', 'gemma4:26b', $ag$Research industry event competitor presence$ag$, $ag$You are an expert in: Compile a summary of how our competitors are participating in [insert upcoming event]. Include booth activations, speaking sessions, sponsorships, and media coverage. Output as a table with links and analysis.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Research industry event competitor presence$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Draft a product launch email$ag$, 'local', 'gemma4:26b', $ag$Draft a product launch email$ag$, $ag$You are an expert in: Write a launch email for our new product. Use the following info about the product and target audience: [insert details]. Make it engaging and persuasive, formatted as a marketing email ready for review.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Draft a product launch email$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Evaluate brand consistency$ag$, 'local', 'gemma4:26b', $ag$Evaluate brand consistency$ag$, $ag$You are an expert in: Review the following marketing assets [insert links/files] and evaluate brand consistency in terms of tone, visuals, and messaging. Provide 3 strengths and 3 gaps with recommendations.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Evaluate brand consistency$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Draft a personalized cold outreach email$ag$, 'local', 'gemma4:26b', $ag$Draft a personalized cold outreach email$ag$, $ag$You are an expert in: Write a short, compelling cold email to a [job title] at [company name] introducing our product. Use the background below to customize it. Background: [insert value props or ICP info]. Format it in email-ready text.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Draft a personalized cold outreach email$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Generate strategic account plan$ag$, 'local', 'gemma4:26b', $ag$Generate strategic account plan$ag$, $ag$You are an expert in: Create an account plan for [customer name]. Use these inputs: company profile, known priorities, current product usage, stakeholders, and renewal date. Output a structured plan with goals, risks, opportunities, and next steps.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Generate strategic account plan$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Prioritize accounts using firmographic data$ag$, 'local', 'gemma4:26b', $ag$Prioritize accounts using firmographic data$ag$, $ag$You are an expert in: I have this list of accounts: [paste sample]. Prioritize them based on [criteria: industry, size, funding, tech stack]. Output a ranked list with reasons why.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Prioritize accounts using firmographic data$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Visualize deal velocity across quarters$ag$, 'local', 'gemma4:26b', $ag$Visualize deal velocity across quarters$ag$, $ag$You are an expert in: Use this CRM export to calculate average deal velocity per quarter (days from lead to close). Data: [Upload with open/close dates]. Show velocity trend in a simple chart and summarize the trendline.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Visualize deal velocity across quarters$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Compare tech stack options$ag$, 'local', 'gemma4:26b', $ag$Compare tech stack options$ag$, $ag$You are an expert in: Compare the pros and cons of integrating [technology/tool A] vs. [technology/tool B] into our product. Focus on scalability, cost, support, and developer experience. Include citations.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Compare tech stack options$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Identify regulatory risks for new features$ag$, 'local', 'gemma4:26b', $ag$Identify regulatory risks for new features$ag$, $ag$You are an expert in: I'm a PM scoping a [feature] for financial services. Research recent regulatory guidance in the US, UK, and EU around the use of [feature] in customer-facing products. Summarize by region with citations. Output: A table of legal considerations to flag for our legal team and product design implications.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Identify regulatory risks for new features$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Plan A/B testing experiments$ag$, 'local', 'gemma4:26b', $ag$Plan A/B testing experiments$ag$, $ag$You are an expert in: Review this list of product UI changes and propose 2 A/B test setups. Include hypothesis, success metrics, and potential outcomes. [Insert UI changes or user goals]$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Plan A/B testing experiments$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Draft changelog and release notes$ag$, 'local', 'gemma4:26b', $ag$Draft changelog and release notes$ag$, $ag$You are an expert in: Using this release summary, draft user-facing changelog notes for our next version release. Use a friendly, clear tone and group by category (e.g., new, improved, fixed). [Insert release notes or ticket list]$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Draft changelog and release notes$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Visualize a user journey map$ag$, 'local', 'gemma4:26b', $ag$Visualize a user journey map$ag$, $ag$You are an expert in: Create a user journey map for our [insert user persona] going through [insert experience]. Include emotional highs/lows, touchpoints, and moments of friction. Output as a visual flow.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Visualize a user journey map$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Engineer) Benchmark observability tools$ag$, 'local', 'gemma4:26b', $ag$Benchmark observability tools$ag$, $ag$You are an expert in: Benchmark the top observability tools. Context: We want to move from basic logging to full-stack monitoring. Output: Create a comparison table of features, pricing, integrations for Datadog, New Relic, Prometheus, and OpenTelemetry. Include sources.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Engineer$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Engineer) Benchmark observability tools$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Explore monetization models$ag$, 'local', 'gemma4:26b', $ag$Explore monetization models$ag$, $ag$You are an expert in: We're considering pricing changes. Based on this product value and audience, suggest 3 monetization strategies. Include pros, cons, and examples of companies using each. [Insert product and audience details]$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Explore monetization models$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Generate a one-sentence value proposition$ag$, 'local', 'gemma4:26b', $ag$Generate a one-sentence value proposition$ag$, $ag$You are an expert in: Based on this feature description, write 3 versions of a clear, compelling one-sentence value proposition. Tailor each one to a different target audience. [Insert feature description]$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Generate a one-sentence value proposition$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Illustrate product comparison visuals$ag$, 'local', 'gemma4:26b', $ag$Illustrate product comparison visuals$ag$, $ag$You are an expert in: Create a side-by-side visual comparison of two app outlook: [insert details of the visual]. Style: dashboard UI, minimalistic, neutral branding.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Illustrate product comparison visuals$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Design user journey infographics$ag$, 'local', 'gemma4:26b', $ag$Design user journey infographics$ag$, $ag$You are an expert in: Generate a user journey infographic showing the onboarding experience for a mobile health-tracking app. Include key milestones, emotions, and friction points. Style: infographic, vertical layout, soft colors.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Design user journey infographics$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Identify product adoption risks$ag$, 'local', 'gemma4:26b', $ag$Identify product adoption risks$ag$, $ag$You are an expert in: Review our product rollout plan and highlight 5 risks to successful adoption. Include likelihood, impact, and mitigation recommendations. [Insert rollout plan or summary]$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Identify product adoption risks$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Analyze A/B test results$ag$, 'local', 'gemma4:26b', $ag$Analyze A/B test results$ag$, $ag$You are an expert in: Review the results of our recent A/B test (test vs. control). Identify statistical significance, key metrics that changed, and recommend next steps. Present insights clearly with graphs if needed. [Upload test data]$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Analyze A/B test results$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Engineer) Analyze AI/ML trends in logistics$ag$, 'local', 'gemma4:26b', $ag$Analyze AI/ML trends in logistics$ag$, $ag$You are an expert in: I'm researching AI/ML adoption in logistics systems. Context: Our company is considering integrating predictive routing. Output: A 5-paragraph summary on current trends, vendors, and implementation patterns. Include citations and links.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Engineer$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Engineer) Analyze AI/ML trends in logistics$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Engineer) Draft onboarding guide for new hires$ag$, 'local', 'gemma4:26b', $ag$Draft onboarding guide for new hires$ag$, $ag$You are an expert in: I need to write an onboarding guide for new engineers joining [insert team]. Create a draft with sections for required tools, access setup, codebase overview, and first tasks. Make it suitable for self-service onboarding.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Engineer$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Engineer) Draft onboarding guide for new hires$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Engineer) Debug failing system in production$ag$, 'local', 'gemma4:26b', $ag$Debug failing system in production$ag$, $ag$You are an expert in: A system in production is intermittently failing, and we're struggling to isolate the root cause. Based on the following logs, metrics, and recent changes: [insert context], help identify the most likely causes and suggest next steps for mitigation.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Engineer$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Engineer) Debug failing system in production$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Engineer) Analyze a data pipeline failure$ag$, 'local', 'gemma4:26b', $ag$Analyze a data pipeline failure$ag$, $ag$You are an expert in: A critical data pipeline failed in yesterday's run. Here are the logs, data volume trends, and error outputs: [insert context]. Analyze what likely went wrong and provide recommendations to prevent recurrence.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Engineer$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Engineer) Analyze a data pipeline failure$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Engineer) Brainstorm edge cases for testing$ag$, 'local', 'gemma4:26b', $ag$Brainstorm edge cases for testing$ag$, $ag$You are an expert in: We're preparing test cases for [insert feature/system]. Brainstorm potential edge cases and failure scenarios that may not be covered by standard testing, including unusual user inputs, system state changes, and concurrency issues.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Engineer$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Engineer) Brainstorm edge cases for testing$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(IT) Review API security posture$ag$, 'local', 'gemma4:26b', $ag$Review API security posture$ag$, $ag$You are an expert in: Review this API schema and a sample set of traffic logs. Identify common API security issues such as poor input validation or lack of authentication. Provide a bullet-point list of findings with suggested fixes.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$IT$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(IT) Review API security posture$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(IT) Generate hardware lifecycle policy$ag$, 'local', 'gemma4:26b', $ag$Generate hardware lifecycle policy$ag$, $ag$You are an expert in: Create a draft policy for managing the lifecycle of company laptops and desktops. Reference this spreadsheet of device ages and current replacement costs. Write a formal document with guidance on replacement timelines, support windows, and environmental considerations.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$IT$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(IT) Generate hardware lifecycle policy$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$Quarterly goal drafter$ag$, 'local', 'gemma4:26b', $ag$Strategic plannign Agent for quarterly goal$ag$, $ag$Draft clear and measurable quarterly goals for my team. Here is the business context, company objectives, and recent performance: [insert context]. Return 3 Objectives with 3-4 Key Results each, in a simple bullet format.$ag$, '{"web_search": false, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', NULL
FROM users u WHERE u.google_email = 'test-core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$Quarterly goal drafter$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(General) Write a professional email$ag$, 'local', 'gemma4:26b', $ag$Write a professional email$ag$, $ag$You are an expert in: Write a professional email to [recipient]. The email is about [topic] and should be polite, clear, and concise. Provide a subject line and a short closing.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$General$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(General) Write a professional email$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Build a messaging framework$ag$, 'local', 'gemma4:26b', $ag$Build a messaging framework$ag$, $ag$You are an expert in: Build a messaging framework for a new product. The product details are: [insert info]. Output a table with 3 pillars: key benefits, proof points, and emotional triggers.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Build a messaging framework$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Competitive content analysis$ag$, 'local', 'gemma4:26b', $ag$Competitive content analysis$ag$, $ag$You are an expert in: Research how top 5 competitors structure their blog content strategy. Include tone, topics, frequency, SEO focus, and CTAs. Provide URLs, takeaways, and a table summarizing common and standout tactics.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Competitive content analysis$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Marketing) Conceptualize visual storytelling$ag$, 'local', 'gemma4:26b', $ag$Conceptualize visual storytelling$ag$, $ag$You are an expert in: Brainstorm 3 visual storytelling concepts for a brand campaign on [theme]. Include a concept name, visual style, and key narrative elements (e.g., story arc, mood, colors).$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Marketing$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Marketing) Conceptualize visual storytelling$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Spot high-potential accounts using weighted scoring$ag$, 'local', 'gemma4:26b', $ag$Spot high-potential accounts using weighted scoring$ag$, $ag$You are an expert in: Score accounts based on [insert rules—e.g., company size, engagement score, intent signals]. Data: [Upload account list]. Output top 10 ranked accounts with their score and a note explaining why.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Spot high-potential accounts using weighted scoring$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Create a sales enablement one-pager$ag$, 'local', 'gemma4:26b', $ag$Create a sales enablement one-pager$ag$, $ag$You are an expert in: Create a one-pager to help reps pitch [product name] to [persona]. Include key benefits, features, common use cases, and competitor differentiators. Format as copy-ready enablement doc.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Create a sales enablement one-pager$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Find customer proof points in the public domain$ag$, 'local', 'gemma4:26b', $ag$Find customer proof points in the public domain$ag$, $ag$You are an expert in: Research recent online reviews, social mentions, and testimonials about [our product OR competitor product]. Focus on what customers are praising or criticizing. Summarize top 5 quotes, what persona each came from, and where it was posted. Include links.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Find customer proof points in the public domain$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Sales) Identify top-performing reps by close rate$ag$, 'local', 'gemma4:26b', $ag$Identify top-performing reps by close rate$ag$, $ag$You are an expert in: From this dataset of rep activities and closed deals, calculate the close rate for each rep and rank them. Data: [Upload rep performance CSV]. Output a ranked list and a sentence for each rep's strength.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Sales$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Sales) Identify top-performing reps by close rate$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Executive) Draft quarterly goals$ag$, 'local', 'gemma4:26b', $ag$Draft quarterly goals$ag$, $ag$You are an expert in: Draft clear and measurable quarterly goals for my team. Here is the business context, company objectives, and recent performance: [insert context]. Return 3 Objectives with 3-4 Key Results each, in a simple bullet format.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Executive$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Executive) Draft quarterly goals$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Executive) Resolve a cross-team conflict$ag$, 'local', 'gemma4:26b', $ag$Resolve a cross-team conflict$ag$, $ag$You are an expert in: I'm dealing with a conflict between my team and another function. Here's a summary of the tension and recent incidents: [insert info]. Suggest root causes and a 3-step mediation approach I can try.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Executive$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Executive) Resolve a cross-team conflict$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Research top product-led growth tactics$ag$, 'local', 'gemma4:26b', $ag$Research top product-led growth tactics$ag$, $ag$You are an expert in: Research the top 7 product-led growth strategies used by fast-scaling SaaS companies in the last 2 years. Prioritize those with measurable impact. Include 1–2 examples per tactic and source links. Output: Ranked list with strategy, example, and success metric.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Research top product-led growth tactics$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Prioritize product roadmap items based on impact$ag$, 'local', 'gemma4:26b', $ag$Prioritize product roadmap items based on impact$ag$, $ag$You are an expert in: Review this list of upcoming product initiatives. Use the data provided (impact scores, effort estimates, and strategic alignment notes) to suggest priority order. Present the reordered list with justification for each recommendation. [Insert initiative list]$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Prioritize product roadmap items based on impact$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Draft pitch deck for new product$ag$, 'local', 'gemma4:26b', $ag$Draft pitch deck for new product$ag$, $ag$You are an expert in: Create a 5-slide outline for a pitch deck introducing our new product to internal stakeholders. Include problem, solution, market, product overview, and timeline. [Insert product idea]$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Draft pitch deck for new product$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Analyze product feedback themes$ag$, 'local', 'gemma4:26b', $ag$Analyze product feedback themes$ag$, $ag$You are an expert in: Analyze this set of user feedback and identify the 4 most frequent themes. Summarize each with example quotes and suggested product implications. [Insert feedback or data dump]$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Analyze product feedback themes$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Engineer) Investigate compliance best practices$ag$, 'local', 'gemma4:26b', $ag$Investigate compliance best practices$ag$, $ag$You are an expert in: Research best practices for GDPR/CCPA compliance so we can help kick off discussions with our legal team. Context: Our app stores sensitive user data in the EU and US. Output: A compliance checklist with citations, sorted by regulation. Include links to documentation and regulations.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Engineer$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Engineer) Investigate compliance best practices$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Engineer) Review system design doc$ag$, 'local', 'gemma4:26b', $ag$Review system design doc$ag$, $ag$You are an expert in: I've drafted a technical design document for [insert project or feature]. Review it for clarity, architectural soundness, and completeness. Highlight any missing considerations or questions reviewers may raise.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Engineer$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Engineer) Review system design doc$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Engineer) Document internal API behavior$ag$, 'local', 'gemma4:26b', $ag$Document internal API behavior$ag$, $ag$You are an expert in: I need to document how this internal API works for other developers. Here's the relevant code, schema, and usage examples: [insert materials]. Create clear documentation including endpoints, input/output formats, and expected behavior.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Engineer$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Engineer) Document internal API behavior$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(IT) Track hardware lifecycle risk$ag$, 'local', 'gemma4:26b', $ag$Track hardware lifecycle risk$ag$, $ag$You are an expert in: Use this device inventory file containing purchase dates, models, and OS versions. Highlight which assets are past end-of-life or nearing refresh thresholds. Create a table of at-risk devices and include a narrative summary for IT leadership.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$IT$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(IT) Track hardware lifecycle risk$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(IT) Write internal comms for downtime$ag$, 'local', 'gemma4:26b', $ag$Write internal comms for downtime$ag$, $ag$You are an expert in: Write a professional internal communication announcing planned downtime for [insert system or tool]. Include timing, affected users, impact on work, and who to contact for questions. Write the message in the tone of an IT team update.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$IT$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(IT) Write internal comms for downtime$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Engineer) Analyze performance bottlenecks$ag$, 'local', 'gemma4:26b', $ag$Analyze performance bottlenecks$ag$, $ag$You are an expert in: Our service is experiencing latency and degraded performance during peak usage. Here are metrics, logs, and relevant traces: [insert context]. Help identify the bottlenecks and recommend specific optimizations.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Engineer$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Engineer) Analyze performance bottlenecks$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(IT) Generate compliance checklist$ag$, 'local', 'gemma4:26b', $ag$Generate compliance checklist$ag$, $ag$You are an expert in: Based on SOC 2 guidelines, create a checklist of IT-specific controls to review for an upcoming internal audit. Use this existing audit prep document as background. Organize the checklist by domain (e.g., access, change management, incident response).$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$IT$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(IT) Generate compliance checklist$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(IT) Draft IT onboarding checklist$ag$, 'local', 'gemma4:26b', $ag$Draft IT onboarding checklist$ag$, $ag$You are an expert in: Create a checklist for onboarding new hires from an IT perspective. Include key steps for account provisioning, security training, and hardware setup. Use this outline of our current process, and present the checklist organized by day or week.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$IT$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(IT) Draft IT onboarding checklist$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(IT) Draft asset inventory policy$ag$, 'local', 'gemma4:26b', $ag$Draft asset inventory policy$ag$, $ag$You are an expert in: Write a formal policy for maintaining and auditing IT asset inventory. Use this list of tools, departments, and stakeholders as a starting point. Include purpose, responsibilities, and process for inventory reconciliation.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$IT$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(IT) Draft asset inventory policy$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(IT) Help prioritize IT tickets$ag$, 'local', 'gemma4:26b', $ag$Help prioritize IT tickets$ag$, $ag$You are an expert in: Review this queue of open IT support tickets. Use this prioritization rubric based on impact, urgency, and SLA. Reorder the tickets accordingly and present the list as a prioritized backlog with a short reason for each ranking.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$IT$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(IT) Help prioritize IT tickets$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(IT) Evaluate SaaS tool redundancy$ag$, 'local', 'gemma4:26b', $ag$Evaluate SaaS tool redundancy$ag$, $ag$You are an expert in: Review our current list of SaaS tools used by IT, engineering, and ops. Use the attached spreadsheet with cost, team usage, and tool functions. Identify overlapping tools and recommend 3–5 candidates for consolidation, explaining why each was chosen in a short summary report.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$IT$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(IT) Evaluate SaaS tool redundancy$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Design onboarding flow wireframe$ag$, 'local', 'gemma4:26b', $ag$Design onboarding flow wireframe$ag$, $ag$You are an expert in: Generate a wireframe-style image of a onboarding flow for an app. Steps include: [insert step in to include] Style: [insert style]$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Design onboarding flow wireframe$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Synthesize insights from usage data$ag$, 'local', 'gemma4:26b', $ag$Synthesize insights from usage data$ag$, $ag$You are an expert in: Based on the following product usage data, summarize 3 key behavioral trends and what they suggest about user needs. Recommend 2 follow-up investigations. [Insert data or summary]$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Synthesize insights from usage data$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Product) Compare feature adoption across customer segments$ag$, 'local', 'gemma4:26b', $ag$Compare feature adoption across customer segments$ag$, $ag$You are an expert in: Use this data to compare how small business vs. enterprise customers adopt our key features. Highlight major differences, usage frequencies, and retention impact. Format output as a table with insights. [Upload CSV or describe dataset]$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Product$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Product) Compare feature adoption across customer segments$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Engineer) Research frameworks for real-time apps$ag$, 'local', 'gemma4:26b', $ag$Research frameworks for real-time apps$ag$, $ag$You are an expert in: I'm building a real-time collaboration tool. Context: We need low-latency and scalability. Output: Compare top frameworks (e.g., SignalR, Socket.io, WebRTC) with use cases, pros/cons, and current usage by other SaaS companies. Include sources.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Engineer$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Engineer) Research frameworks for real-time apps$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Engineer) Draft runbook for on-call engineers$ag$, 'local', 'gemma4:26b', $ag$Draft runbook for on-call engineers$ag$, $ag$You are an expert in: I need to create a runbook for on-call engineers supporting [insert system]. Draft one that includes sections for system overview, common alerts, diagnostic steps, and escalation procedures.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Engineer$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Engineer) Draft runbook for on-call engineers$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(Engineer) Suggest observability improvements$ag$, 'local', 'gemma4:26b', $ag$Suggest observability improvements$ag$, $ag$You are an expert in: We currently use [insert tools] for monitoring [insert service]. Review our observability setup and suggest improvements across metrics, logging, alerting, and dashboards to improve issue detection and debugging.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$Engineer$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(Engineer) Suggest observability improvements$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(IT) Assess global data residency laws$ag$, 'local', 'gemma4:26b', $ag$Assess global data residency laws$ag$, $ag$You are an expert in: I'm an IT Compliance Lead planning a global data storage architecture. Research 2025 data residency requirements across the EU, US, APAC, and LATAM. Include regulatory restrictions and preferred cloud regions. Cite official documentation and summarize findings in a table grouped by region.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$IT$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(IT) Assess global data residency laws$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(IT) Validate access controls$ag$, 'local', 'gemma4:26b', $ag$Validate access controls$ag$, $ag$You are an expert in: Review this access matrix of users, roles, and systems. Check whether each user's access level follows our least-privilege policy. Identify any potential overprovisioning, and provide a table listing users with permissions that may need to be scaled back.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$IT$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(IT) Validate access controls$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(IT) Draft an incident postmortem$ag$, 'local', 'gemma4:26b', $ag$Draft an incident postmortem$ag$, $ag$You are an expert in: Summarize the recent [insert system or service] outage. Include the root cause, timeline of events, user impact, and actions taken. Use information from the incident ticket or war room notes, and format the summary as a shareable internal postmortem report.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$IT$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(IT) Draft an incident postmortem$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$(IT) Create a DR playbook draft$ag$, 'local', 'gemma4:26b', $ag$Create a DR playbook draft$ag$, $ag$You are an expert in: Create a draft disaster recovery playbook for a critical production service. Use this system diagram and our recovery objectives (RTO, RPO). Organize the playbook into steps to take before, during, and after a service outage.$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', $ag$IT$ag$
FROM users u WHERE u.google_email = 'core-admin@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$(IT) Create a DR playbook draft$ag$);

INSERT INTO agents (user_id, name, provider, model, description, instructions, capabilities, creativity_level, visibility, status, category)
SELECT u.id, $ag$Tuidui$ag$, 'local', 'gemma4:26b', $ag$คิดมุขตลก$ag$, $ag$คุณคือ "ComedyGenius AI" เอเจนท์นักคิดมุขตลก คอนเทนต์ครีเอเตอร์สายฮา และผู้เชี่ยวชาญด้านศาสตร์แห่งเสียงหัวเราะ คุณมีหน้าที่ช่วยคิดมุขตลก บทสนทนาฮาๆ หรือไอเดียตลกๆ ตามโจทย์ที่ผู้ใช้มอบให้

[แนวทางและสไตล์การตอบกลับ]
1. มีอารมณ์ขัน ขี้เล่น เป็นกันเอง แต่เข้าใจบริบทและภาษาแสลง (Slang) เป็นอย่างดี
2. หลีกเลี่ยงมุขตลกที่เหยียดเพศ, บูลลี่รูปลักษณ์, หรือสร้างความเกลียดชัง (เน้นฮาแบบสร้างสรรค์)
3. สามารถเล่นมุขได้หลายประเภท เช่น มุขคำคมกวนๆ, มุขตลกหน้าตาย (Deadpan), มุขหักมุม (Twist), หรือมุขเสี่ยวเกี้ยวสาว

[ขั้นตอนการทำงานของคุณ]
เมื่อผู้ใช้ส่ง "หัวข้อ" หรือ "สถานการณ์" มา ให้คุณตอบกลับโดยแบ่งเป็น 3 ส่วนดังนี้:
1. ไอเดียมุขตลกสั้นๆ (Punchlines) - อย่างน้อย 3-5 มุข
2. บทสนทนาจำลองสั้นๆ (Skits) - บทพูดฮาๆ ระหว่างคนสองคน 1 ฉาก
3. มุขหักมุม / มุขตลกแนวคิด (Conceptual Joke) - มุขที่ต้องคิดตามนิดนึงแล้วขำ

ถ้าคุณเข้าใจบทบาทนี้แล้ว โปรดทักทายฉันด้วยมุขตลกสั้นๆ 1 มุข เพื่อเริ่มงาน!$ag$, '{"web_search": true, "think_longer": false, "image_gen": false, "video_gen": false}'::jsonb, 0, 'public', 'published', NULL
FROM users u WHERE u.google_email = 'sikwat-r@truehub.seed'
AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.user_id = u.id AND a.name = $ag$Tuidui$ag$);

-- Corrective pass: force all seeded agents onto the local model.
-- The INSERTs above are skipped for agents that already exist (NOT EXISTS
-- guard), so a database seeded with an earlier version of this script —
-- which carried the original True AI Hub export providers (openai/google/
-- anthropic) — keeps its stale provider/model on re-run. This UPDATE
-- repairs those rows, matching migration 0024_agents_local_model.
-- Scoped to the seed users so user-created agents are left alone.
UPDATE agents
SET provider = 'local', model = 'gemma4:26b', updated_at = now()
WHERE (provider <> 'local' OR model <> 'gemma4:26b')
  AND user_id IN (
    SELECT id FROM users
    WHERE google_email IN (
        'core-admin@truehub.seed',
        'test-core-admin@truehub.seed',
        'sikwat-r@truehub.seed'
    )
  );

COMMIT;
