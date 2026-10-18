Signature Watermark - Windows native blind-watermark workflow

Requirements
------------
- Windows
- Python 3.12 available through "py -3.12"
- Transparent master signature saved as signature.png

Install
-------
1. Copy these files to D:\signature-watermark
2. Keep signature.png in that folder.
3. Double-click setup.bat once.
4. Edit .env and replace WATERMARK_PASSWORD.
5. Double-click run-signature-watermark.bat.

Runtime background menu
-----------------------
1. White
   Opaque white rectangle. Strongest/simple carrier; most visible on non-white documents.

2. Translucent
   Uniform semi-transparent white carrier.

3. Feathered
   Semi-transparent white carrier that fades to transparent at the edges.

4. Feathered texture [recommended]
   Feathered carrier plus very weak microtexture.

Output
------
out\images\SIG-*.png
out\images\signature_watermarked.png
out\watermark\SIG-*.txt
out\watermark\watermark.txt

Watermark
---------
Only an 8-character short ID such as W12AB34C is embedded with
guofei9987/blind_watermark. Full purpose/date/settings are kept locally
in the matching TXT file.

Extract
-------
- Double-click extract-watermark.bat for the latest image.
- Drag a PNG/JPG onto extract-watermark.bat to try extracting from it.
- If the image was only resized, the extractor uses saved dimensions to restore it.
- For a full-page screenshot, crop to the signature/carrier area first.

Robustness test
---------------
Double-click test-watermark.bat after generating a signature.
It tests:
- flattened-on-white PNG
- 75% resize
- 50% resize
- JPEG quality 90

These are synthetic checks and are not a guarantee for every screenshot,
camera photo, crop, perspective transform, or document renderer.
