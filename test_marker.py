from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered

converter = PdfConverter(artifact_dict=create_model_dict())
rendered = converter('test_paper_RA.pdf')
text, _, _ = text_from_rendered(rendered)

# save full output
with open('marker_output.md', 'w', encoding='utf-8') as f:
    f.write(text)

print("Total length:", len(text))
print("\nFirst 300 chars:")
print(text[:300])

# find equations
idx = text.find('$$')
print(f"\nFirst $$ equation at index: {idx}")
if idx >= 0:
    print(text[max(0, idx-100):idx+300])