# Phase 1 licenses

Checked on 2026-09-29 against the pages named here. Re-check the official page before a paper or a public demo. The machine-readable copy is `datasets/metadata/license_log.json`, written by the download scripts.

Phase 1 does not redistribute dataset bytes. They stay in gitignored `datasets/raw/`.

## NYU Depth V2

- Source: https://cs.nyu.edu/~fergus/datasets/nyu_depth_v2.html
- License: no SPDX identifier on the dataset page. Use is the academic use described there. Cite Silberman, Kohli, Hoiem, and Fergus, ECCV 2012, if you use the data.
- Files: `nyu_depth_v2_labeled.mat`, `splits.mat`.

## SUN RGB-D

- Source: https://rgbd.cs.princeton.edu/
- License: no SPDX identifier on the dataset page. The page requires citation of Song, Lichtenberg, and Xiao, CVPR 2015, and of NYU Depth V2, Berkeley B3DO, and SUN3D.
- Files: `SUNRGBD.zip`, `SUNRGBDtoolbox.zip`, `SUNRGBDMeta2DBB_v2.mat`.

## Places365-Standard

- Source of the file list and the terms: http://places2.csail.mit.edu/download-private.html
- The public download page (http://places2.csail.mit.edu/download.html) now points legacy users at a Google form. Phase 1 uses the legacy direct URLs only after `--accept-terms`.

The legacy page says that by downloading the image data you agree to these terms:

- You will use the data only for non-commercial research and educational purposes.
- You will not distribute the images.
- Massachusetts Institute of Technology makes no representations or warranties regarding the data, including warranties of non-infringement or fitness for a particular purpose.
- You accept full responsibility for your use of the data and shall defend and indemnify Massachusetts Institute of Technology, including its employees, officers and agents, against any and all claims arising from your use of the data, including your use of any copies of copyrighted images that you may create from the data.

Passing `--accept-terms` is the record that you accept those terms for this project. The script does not submit the Google form.

## CubiCasa5K

- Source: https://zenodo.org/records/2613548
- Zenodo license id on 2026-09-29: `cc-by-nc-sa-4.0`
- Legal code: https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode
- The blueprint table and the phase plan call this CC BY-NC 4.0. The Zenodo record is CC BY-NC-SA 4.0, which adds ShareAlike: if you share adaptations, you share them under the same license, and you must give attribution. Both the non-commercial term and the ShareAlike term apply to the zip we would download.
- MD5 `0ce0b203d1e3c125b51087b219bd23b9`, 5469495706 bytes.

Do not treat this dataset as commercial-use data.

## 3D-FRONT and 3D-FUTURE

- Agreement: "3D-FRONT Data Sets Use License Agreement", version June 18, 2020, Tao Bao (China) Software Co., Ltd.
- Terms PDF checked on 2026-09-29: https://gw.alicdn.com/bao/uploaded/TB1ZJUfK.z1gK0jSZLeXXb9kVXa.pdf
- Named Tianchi page: https://tianchi.aliyun.com/specials/promotion/alibaba-3d-scene-dataset (HTTP 404 on that date)
- Grant, from the PDF: a worldwide, revocable, non-exclusive, non-transferable, royalty-free license, with no right to sub-license, for scientific research only. You may download, reproduce, use internally, modify, and edit the data sets, and you may create derivative works.
- Restrictions stated in the PDF: no commercialization of the data sets; no distribution of the data sets to a third party; no use of the data sets, derivative works, or results to commercialize or provide external services; cite the source when disclosing research results or sharing derivative works; keep the agreement and copyright notices with the data; the "no lawsuit against Tao Bao or its affiliates" clause in section 3.3.7.
- Status: not downloaded. You must sign and request the links yourself. See `docs/DATASETS.md`.

## Structured3D

- Source: https://structured3d-dataset.org/
- Data license: the Structured3D Terms of Use at https://drive.google.com/open?id=13ZwWpU_557ZQccwOUJ8H5lvXD7MeZFMa
- Agreement form: https://forms.gle/LXg4bcjC2aEjrL9o8
- The visualization code at https://github.com/bertjiazheng/Structured3D is MIT. That MIT license does not cover the data.
- Status: the agreement form was completed. Phase 1 downloads the four zips named in `docs/DATASETS.md` from the link list. The other zips in that list are not downloaded.

## Objaverse

- Package: `objaverse` 0.1.7, Apache-2.0 on PyPI for the code.
- Objects: https://huggingface.co/datasets/allenai/objaverse
- The package README says use of the Objaverse-XL dataset as a whole is ODC-By 1.0, and that individual objects have their own licenses.
- Phase 1 logs each selected GLB's metadata `license` field (Sketchfab values such as `by` or `by-nc` in the metadata JSON). ODC-By is not a substitute for that per-asset field.
- Status: GLBs not downloaded until `--confirm-download`. The category list is `datasets/metadata/objaverse_furniture_categories.json`.

## FurniScene

- Paper: https://arxiv.org/abs/2401.03470
- The paper's arXiv license is the non-exclusive distribution license for the article, not a dataset license.
- No public dataset download and no dataset license were found on 2026-09-29. The abstract says the dataset and code will be publicly available soon.
- Status: skipped.

## 2010 ADA Standards

- PDF: https://www.ada.gov/assets/pdfs/2010-design-standards.pdf
- HTML: https://www.ada.gov/law-and-regs/design-standards/2010-stds/
- License: U.S. government work. Works of the United States Government are not subject to copyright under 17 U.S.C. § 105. The Department of Justice and the U.S. Access Board published these standards.
- The hand-written summary `datasets/metadata/rag/ada_clearances.md` cites section numbers. It is not a copy of the standard.

## MoHUA Harmonised Guidelines 2021

- PDF used here: https://niua.in/intranet/sites/default/files/2262.pdf (66195648 bytes, SHA-256 recorded in `datasets/metadata/acquisition_log.json`)
- This is the Harmonised Guidelines and Standards for Universal Accessibility in India, 2021, published by the Ministry of Housing and Urban Affairs. The NIUA host is the copy downloaded here. `cpwd.gov.in` rejected the request from this network.
- Copyright notice on page 2 of that PDF: "Copyright © 2021 Gaurav Raheja, IIT Roorkee, NIUA and MoHUA" and "All rights reserved. No part of this publication may be reproduced, stored in a retrieval system or transmitted in any form or by any means whether electronic, mechanical photocopying, recording or otherwise, without due acknowledgements or prior written permission of the authors / Ministry of Housing and Urban Affairs."
- Phase 1 stores the PDF locally for later retrieval and writes short original notes that cite section numbers. It does not copy chapters into the repository.
- The hand-written summary `datasets/metadata/rag/mohua_clearances.md` cites the guideline. It is not a copy of the book.

## Hand-written summaries

`datasets/metadata/rag/ada_clearances.md`, `mohua_clearances.md`, and `ergonomics.md` are short original notes for the future RAG corpus. Each numeric rule names the source section it came from. They are project text, not a substitute for the PDFs.
