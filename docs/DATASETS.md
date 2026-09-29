# Phase 1 dataset acquisition

Phase 1 records where each PhotoSpace dataset comes from, which files we take, and how to download them. Cleaning, class lists, YOLO labels, and database loads are later phases.

Checked on 2026-09-29. Sizes below are `Content-Length` or the publisher's API size from that day, unless a row says otherwise.

Disk budget for this phase is about 80–90 GB. This machine had about 199 GB free on `/` when the scripts were added. Every download script refuses a file that would leave less than 5 GiB free.

Dataset bytes go under `datasets/raw/` and stay gitignored. The tracked records are this file, `docs/LICENSES.md`, and `datasets/metadata/`.

## How to run a download

From the repository root, with the project virtualenv:

```bash
uv run python scripts/download_nyu_depth_v2.py
uv run python scripts/verify_datasets.py
```

A file of 1 GiB or more is skipped unless you pass `--confirm-large`. Places365 is also skipped unless you pass `--accept-terms`, because the legacy download page says that downloading the images accepts their terms.

`scripts/verify_datasets.py` checks every catalog file that is on disk (size, magic, published MD5, and the SHA-256 in `datasets/metadata/acquisition_log.json`) and checks that `datasets/metadata/license_log.json` has one complete entry per dataset. Exit code 2 means the license log is complete and some Phase 1 archives are still waiting on approval. Exit code 1 means a file that should already be valid failed a check, or the license log is incomplete.

## NYU Depth V2 (labeled)

- Page: https://cs.nyu.edu/~fergus/datasets/nyu_depth_v2.html
- Script: `scripts/download_nyu_depth_v2.py`
- Cite: Silberman, Kohli, Hoiem, and Fergus, "Indoor Segmentation and Support Inference from RGBD Images", ECCV 2012.

| File | Bytes | Gate |
| --- | ---: | --- |
| `datasets/raw/nyu_depth_v2/nyu_depth_v2_labeled.mat` | 2972037809 | `--confirm-large` |
| `datasets/raw/nyu_depth_v2/splits.mat` | 2626 | direct |

The labeled page links the `.mat` (about 2.8 GB). It does not link `splits.mat`. That split file is the official train/test index on the same host, from the indoor-segmentation supplement:

https://horatio.cs.nyu.edu/mit/silberman/indoor_seg_sup/splits.mat

The raw capture (about 428 GB) is not part of Phase 1. No MD5 is published for the labeled `.mat`. The script records SHA-256 after a size and MATLAB-header check.

## SUN RGB-D

- Page: https://rgbd.cs.princeton.edu/
- Script: `scripts/download_sun_rgbd.py`
- Cite: Song, Lichtenberg, and Xiao, CVPR 2015, and the NYU Depth V2, B3DO, and SUN3D papers named on that page.

| File | Bytes | Gate |
| --- | ---: | --- |
| `datasets/raw/sun_rgbd/SUNRGBD.zip` | 6885481608 | `--confirm-large` |
| `datasets/raw/sun_rgbd/SUNRGBDtoolbox.zip` | 570324301 | direct |
| `datasets/raw/sun_rgbd/SUNRGBDMeta2DBB_v2.mat` | 4300305 | direct |

The toolbox and the image zip are on `rgbd.cs.princeton.edu`. `SUNRGBD.zip`, the toolbox, and `SUNRGBDMeta2DBB_v2.mat` are on disk. `SUNRGBDMeta3DBB_v2.mat` is on the same site and is not downloaded in Phase 1.

## Places365-Standard (256×256)

- Legacy file list: http://places2.csail.mit.edu/download-private.html
- Public page: http://places2.csail.mit.edu/download.html
- Script: `scripts/download_places365.py`

The public page no longer lists the archives. It asks people who need the legacy Places365 data to sign a Google form. The legacy page still publishes these direct files and says that downloading them accepts the terms in `docs/LICENSES.md`.

| File | Bytes | MD5 | Gate |
| --- | ---: | --- | --- |
| `datasets/raw/places365/train_256_places365standard.tar` | 26103685120 | `53ca1c756c3d1e7809517cc47c5561c5` | `--confirm-large` and `--accept-terms` |
| `datasets/raw/places365/val_256.tar` | 525158400 | `e27b17d8d44f4af9a78502beb927f808` | `--accept-terms` |

These are the full 256×256 train and val archives. Phase 1 does not choose indoor class names, extract a subset, balance classes, or remove duplicates. That work is Phase 2a. The train archive was paused on 2026-09-29 and its partial file was removed. The MIT terms forbid distributing the images, so there is no torrent for it. The val archive is still downloaded. The official train file, if resumed later, is https://data.csail.mit.edu/places/places365/train_256_places365standard.tar (MD5 `53ca1c756c3d1e7809517cc47c5561c5`).

Phase 2a found that `val_256.tar` holds 36,500 images and no labels or category names. With approval, two small official text files were added to `datasets/raw/places365/` (script `scripts/download_places365_labels.py`): `categories_places365.txt` (6833 bytes, from the Places365 GitHub repository) and `places365_val.txt` (1120499 bytes, read as one member of `filelist_places365-standard.tar` with HTTP Range requests, so the rest of that tar was not downloaded). Both are checksummed in `acquisition_log.json`.

High-resolution archives, the test set, and the 6.2-million-image challenge set are not part of Phase 1.

## CubiCasa5K

- Record: https://zenodo.org/records/2613548
- DOI: https://doi.org/10.5281/zenodo.2613548
- Script: `scripts/download_cubicasa5k.py`

| File | Bytes | MD5 | Gate |
| --- | ---: | --- | --- |
| `datasets/raw/cubicasa5k/cubicasa5k.zip` | 5469495706 | `0ce0b203d1e3c125b51087b219bd23b9` | `--confirm-large` |

Zenodo's license id on 2026-09-29 is `cc-by-nc-sa-4.0` (CC BY-NC-SA 4.0). The blueprint and the phase plan say CC BY-NC 4.0. The extra term is ShareAlike. The zip stays unfetched until you confirm `--confirm-large` with that license in mind.

## 3D-FRONT and 3D-FUTURE (manual)

Script: `scripts/download_3d_front.py` (writes the license log only).

The agreement is the "3D-FRONT Data Sets Use License Agreement", version June 18, 2020, with Tao Bao (China) Software Co., Ltd. It is a scientific-research license: no commercialization, and no redistribution of the data sets. Signing is a click on the Tianchi page or a signature on the PDF (name, email, affiliation, signature, date).

What is true on 2026-09-29:

1. https://tianchi.aliyun.com/specials/promotion/alibaba-3d-scene-dataset returns HTTP 404. That is the URL printed in the agreement and in the phase plan.
2. The terms PDF is still hosted at https://gw.alicdn.com/bao/uploaded/TB1ZJUfK.z1gK0jSZLeXXb9kVXa.pdf (61291 bytes, title "3D-FRONT Data Sets Use License Agreement").
3. BlenderProc 2.7.0 still documents this procedure: download that terms PDF, email `3dfront@list.alibaba-inc.com` with your name and affiliation, attach the PDF, and say that you agree. They reply with three links. Approval can take days.

What you need to do:

1. Read the terms PDF.
2. If you agree, sign it and send it yourself. This project will not invent credentials or send the email for you.
3. When the links arrive, tell me. Phase 1 will then take:
   - the house/scene JSON archive (BlenderProc's `3D-FRONT` folder, one JSON per house)
   - `model_info.json` (BlenderProc says this file, plus `categories.py`, is in the 3D-FUTURE unzip)
   - only the furniture model directories referenced by the scene JSONs we keep
4. Do not take the texture archive in Phase 1.
5. If `model_info.json` is only inside a multi-gigabyte furniture zip, stop and ask before downloading that zip.

## Structured3D

Script: `scripts/download_structured3d.py --confirm-large`

Official page: https://structured3d-dataset.org/

The agreement form was completed, and the link list names every zip. Phase 1 downloads only these four, from `https://zju-kjl-jointlab-azure.kujiale.com/Structured3D/`:

| File | Bytes |
| --- | ---: |
| `datasets/raw/structured3d/Structured3D_annotation_3d.zip` | 39392097 |
| `datasets/raw/structured3d/Structured3D_bbox.zip` | 1142587307 |
| `datasets/raw/structured3d/Structured3D_perspective_full_00.zip` | 12626434579 |
| `datasets/raw/structured3d/Structured3D_perspective_full_01.zip` | 14242379576 |

Panorama zips, empty-room zips, and perspective parts `02`–`17` are not downloaded. Part `09` is marked corrupted in the link list. Perspective parts `00` and `01` were paused and their partials were removed on 2026-09-29. The Structured3D terms forbid redistributing the files, so the Azure links above are the allowed download. A download manager on those two URLs is the faster option.

The folder layout after unzip is documented at https://github.com/bertjiazheng/Structured3D/blob/master/data_organization.md. Official splits there are scenes `00000`–`02999` train, `03000`–`03249` val, and `03250`–`03499` test. Phase 1 does not filter scenes.

## Objaverse (waiting on approval)

Script: `scripts/download_objaverse.py`

Package: `objaverse==0.1.7` (`load_lvis_annotations`, `load_annotations`, `load_objects`). The GLB download does not start until:

```bash
uv add objaverse==0.1.7
uv run python scripts/download_objaverse.py --confirm-download
```

The furniture keys are the 36 LVIS names in `datasets/metadata/objaverse_furniture_categories.json`, read from `lvis-annotations.json.gz` on 2026-09-29. The script round-robins sorted uids until 160 GLBs. It logs each asset's metadata `license` field to `datasets/metadata/objaverse_asset_licenses.jsonl`. Bytes go under `datasets/raw/objaverse/`. The script stops if free space falls below 8 GiB.

## FurniScene (skipped)

Script: `scripts/download_furniscene.py`

Paper: https://arxiv.org/abs/2401.03470 (v2, 6 May 2024). The abstract still says "Our dataset and code will be publicly available soon." A web search on 2026-09-29 found no official download or repository. There is no public license to record beyond that sentence. FurniScene is skipped and does not block Phase 1.

## RAG corpus (public documents only)

Script: `scripts/download_rag_corpus.py`

| File | Bytes | Source |
| --- | ---: | --- |
| `datasets/raw/rag/2010-ada-design-standards.pdf` | 4208963 | https://www.ada.gov/assets/pdfs/2010-design-standards.pdf |
| `datasets/raw/rag/mohua-harmonised-guidelines-2021.pdf` | 66195648 | https://niua.in/intranet/sites/default/files/2262.pdf |

`https://cpwd.gov.in/Publication/HG2021_MOHUAN.pdf` returned a web-application-firewall rejection from this network, so the MoHUA 2021 guidelines are taken from the NIUA host of the same document.

Hand-written summaries, each citing its source, live in:

- `datasets/metadata/rag/ada_clearances.md`
- `datasets/metadata/rag/mohua_clearances.md`
- `datasets/metadata/rag/ergonomics.md`

No retailer catalog is scraped.

## Planned bytes if every direct archive is approved

| Group | Bytes |
| --- | ---: |
| NYU labeled + splits | 2972040435 |
| SUN RGB-D zip + toolbox + 2D boxes | 7460106214 |
| Places365 train + val 256 | 26628843520 |
| CubiCasa5K | 5469495706 |
| ADA + MoHUA PDFs | 70404611 |
| **Direct total** | **42590890486** (about 42.6 GB) |

That direct total is inside the 90 GB budget (`90000000000` bytes in the catalog). The four Structured3D zips add about 26.1 GB and were started after the agreement link list arrived. 3D-FRONT is deferred. Objaverse is the 160-GLB furniture subset.
