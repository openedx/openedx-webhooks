"""Small bits of templates for use in tests."""

# Text in the bot comment for external contributors.
EXTERNAL_TEXT = "<!-- comment:external_pr -->"

# Text in the bot comment for core committers.
CORE_COMMITTER_TEXT = "<!-- comment:welcome-core-committer -->"

BLENDED_TEXT = "<!-- comment:welcome-blended -->"

# Text in the bot comment if the contributor has no CLA.
NO_CLA_TEXT = "<!-- comment:no_cla -->"

# A link in the bot comment if the contributor has no CLA.
NO_CLA_LINK = (
    "[signed contributor agreement]" +
    "(https://open.edx.org/wp-content/uploads/2019/01/individual-contributor-agreement.pdf)"
)

# Text in the bot comment if the contributor is a contractor.
CONTRACTOR_TEXT = "<!-- comment:contractor -->"
