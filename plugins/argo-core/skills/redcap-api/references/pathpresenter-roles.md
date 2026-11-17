---
name: pathpresenter-roles
description: ARGO's standard PathPresenter roles — Admin for the ARGO admin, Guest for everyone else, the per-dataset roles and switches, the annotation-project switches, and who gets what on a new study. The PathPresenter counterpart of [[standard-roles]].
---

# PathPresenter roles at ARGO

PathPresenter has **three places** where access is set, and the ARGO admin sets all of them; the
admin creates every account, every dataset and every annotation project (decided 2026-11-17):

1. **An account role**: one per person, on the Users page. It decides what someone can do
   *anywhere* on the instance.
2. **Dataset roles and switches**: set on each dataset. They decide what someone can do with *that
   study's slides*. Nobody sees a dataset until it is shared with them.
3. **Annotation-project settings**: set on the readers' project. They decide whose annotations a
   reader can see.

The account role stays coarse; the per-study job lives on the dataset. Source: the vendor's role
table and sharing workflows (Research portal release, 2026), checked against our instances.

## Account roles: only the ARGO admin can create anything

**Nobody but the ARGO admin creates datasets** (decided 2026-11-17). In PathPresenter, every
account role that can manage access (Admin, Institutional Admin, Principal Investigator, Honest
Broker) can also create datasets, so none of them is given out. The dataset screen says so: only
those four are eligible as Dataset Access Manager.

| Account role | What it can do, in plain words | At ARGO |
|---|---|---|
| **Admin** | Everything: people, datasets, annotation projects, eCRFs, institutes, Results, audit log, settings | **The ARGO admin only** |
| **Guest** | Sees only what is shared with it; annotates projects it is assigned to | **Everyone else**: PIs, PMs, RAs, readers, viewers |
| **Internal Researcher** | Sees only what is shared; annotates; creates its own eCRFs; co-owns a project if added | PathPresenter vendor support only |
| Principal Investigator | Creates datasets and annotation projects; sees Results | **Not used**: can create datasets |
| Honest Broker | Creates, edits and deletes datasets | **Not used**: can create and delete datasets |
| Institutional Admin | Manages one institution's users; creates datasets | **Not used** |
| External User | Self-registers on the login page | **Not used**: the ARGO admin creates every account |

What follows from this:
- **The ARGO admin owns every dataset and is its only Access Manager**: access requests come to
  the admin.
- **The ARGO admin builds every annotation project and eCRF** (a Guest can't own one), and
  readers' **results leave PathPresenter as the admin's export** (only Admin and PI see Results).
- **Slides can't be moved or copied between datasets.** Data Contributor, Honest Broker and Admin
  all failed on our instance (2026-11-17). An analysis study therefore gets no new dataset: its
  annotation project is built on the dataset the slides already sit in, using only the listed
  slides, and that dataset is shared with the study's readers.
- Accounts created before this rule with a dataset-creating role (Honest Broker, extra Admins) are
  moved to Guest once their uploads are confirmed to work through the dataset jobs below.

## Per-dataset roles

| On the dataset | What it gives | Typical holder |
|---|---|---|
| **Owner** | The dataset creator: all dataset operations | ARGO admin, always |
| **Dataset Access Manager** | Approves read-only users' requests to view or download | ARGO admin (no other eligible role is given out) |
| **Metadata (Entry) Specialist** | Edits slide metadata only | PM, or the RA who keeps the metadata |
| **Data Contributor** | Uploads slides to this dataset only | PM, scanning-site RA |
| **Approved** access | Opens and views the slides directly | PI, readers |
| **Read-Only** access | Sees the dataset and its file list; must request to view or download | Viewers |

Per-user switches on a shared dataset: **Can View Label** (the photo of the glass slide's label),
**download**, and which **metadata fields** they see.

## Every ARGO dataset is set the same way

| Setting | Value |
|---|---|
| Grant access to all users within your organization | OFF |
| Allow access to External User | OFF |
| General permissions for all External Institute User | OFF |
| Access | Specific users only, each Approved or Read-Only |
| Download | OFF for everyone; the ARGO admin grants it per request |
| Can View Label | OFF for everyone: the label photo can carry a name or hospital number |
| Metadata fields visible (readers, viewers) | Stain and slide type only |
| Metadata fields visible (PM, RA) | All |

The Custom Permission tab is not used. Readers from another institution are
**external-institute users**: their institution is added under Institutes first, then they are
shared the dataset one by one, never through the "all external institute users" switch.

## Every annotation project is set the same way

| Setting | Value |
|---|---|
| Annotation review permission (readers) | OFF, so double reads stay independent; the PI may turn it on for a consensus read |
| Additional Project Owner | None by default; the ARGO admin owns and builds the project |

## Who gets what on a new study

`pathology.py setup` writes this table for each request, with the names it gives:

| Person on the request | Account role | On the dataset |
|---|---|---|
| ARGO admin | Admin | Owner + Dataset Access Manager; builds the annotation project and eCRF |
| PI | Guest | Approved; gets results as the admin's export |
| PM / coordinator | Guest | Approved + Metadata Entry Specialist + Data Contributor |
| RA who uploads | Guest | Data Contributor (+ Metadata Entry Specialist if they keep metadata) |
| Reader | Guest | Approved; assigned to the annotation project; stain and slide type only; no annotation review |
| Viewer | Guest | Read-Only |

Someone without a PathPresenter account is requested on the Study Personnel Request (platform:
PathPresenter); the ARGO admin creates it with the account role above.
