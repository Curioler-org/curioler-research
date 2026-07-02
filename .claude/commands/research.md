Run the Curioler research pipeline for the topic: $ARGUMENTS

Steps:
1. cd to the curioler-research repo root: `C:\Users\Bhavin\Desktop\Git Projects\Curioler-org\curioler-research`
2. Infer the best-fit SEARCH_DOMAIN from the topic using this guide — do not ask the user:
   - Communication: language, speech, AAC, echolalia, PECS, verbal, nonverbal communication
   - Social: joint attention, friendship, peer interaction, social skills, play with others, eye contact
   - Sensory: sensory overload, sensory processing, hyper/hypo sensitivity, meltdown, shutdown, sound/touch/light sensitivity
   - Behaviour: challenging behaviour, aggression, self-injury, repetitive behaviour, stimming, routines, transitions
   - Adaptive: daily living, self-care, toileting, dressing, independence, life skills, cooking, money
   - Motor: gross motor, fine motor, coordination, handwriting, physical skills, movement
   - General: anything that spans multiple domains or doesn't fit cleanly above (e.g. "most important skills", diagnosis, co-occurring conditions, research overviews)
3. Run: `SEARCH_QUERY="<full topic>" SEARCH_DOMAIN="<inferred domain>" python agent/generate_summary.py` (use Bash tool, set env vars inline)
4. Show the saved file path, the inferred domain, and a preview of the frontmatter
5. Run: `git add docs/_summaries/ && git commit -m "research: <topic>" && git push`
6. Report the GitHub Pages URL where it will publish
