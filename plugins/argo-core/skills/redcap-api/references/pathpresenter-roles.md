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
table ("Role Based Access Control Table - Research", sent 2026-11-20) and sharing workflows, checked against our instances.

## Account roles: only the ARGO admin can create anything

**Nobody but the ARGO admin creates datasets** (decided 2026-11-17). In PathPresenter, every
account role that can manage access (Admin, Institutional Admin, Principal Investigator, Honest
Broker) can also create datasets, so none of them is given out. The dataset screen says so: only
those four are eligible as Dataset Access Manager.

| Account role | What it can do, in plain words | At ARGO |
|---|---|---|
| **Admin** | People, institutes, annotation projects, eCRFs, Results, audit log, settings; creates datasets. Sees only the datasets it owns or is shared | **The ARGO admin only** |
| **Guest** | Sees only what is shared with it; annotates projects it is assigned to | **Everyone else**: PIs, PMs, RAs, readers, viewers |
| **Internal Researcher** | Sees only what is shared; annotates; creates its own eCRFs; can be Additional Project Owner; can't be Dataset Access Manager | PathPresenter vendor support only |
| Principal Investigator | Creates datasets and annotation projects; sees Results; can be Dataset Access Manager and Additional Project Owner; edits or deletes only datasets it owns | **Not used** while it can create datasets (see "Pending" below) |
| Honest Broker | Creates datasets; edits and deletes any dataset it owns or is shared | **Not used**: can create and delete datasets |
| Institutional Admin | Manages one institution's users; creates datasets | **Not used** |
| External User | Self-registers on the login page | **Not used**: the ARGO admin creates every account |

What follows from this:
- **The ARGO admin owns every dataset and is its only Access Manager**: access requests come to
  the admin.
- **The ARGO admin builds every annotation project and eCRF** (a Guest can't own one), and
  readers' **results leave PathPresenter as the admin's export** (only Admin and PI see Results).
- **A dataset belongs to the person who created it, not to a role.** Even an Admin doesn't see
  a dataset until its owner shares it (PathPresenter, 2026-11-19).
- **Only a dataset's owner or its Dataset Access Manager can copy slides out of it**; Data
  Contributor and Metadata Entry Specialist can't, whatever the account role. Copying goes in
  two steps: from the source dataset to **My Datasets**, then from My Datasets to a new dataset,
  an existing one or a sub-dataset. So the ARGO admin copies the listed slides into an analysis
  study's new dataset. If someone else owns the source
  dataset, they first make the ARGO admin its Dataset Access Manager.
- **Additional Project Owner** can only be an Admin, Principal Investigator or Internal
  Researcher; not a Guest or Honest Broker.
- Accounts created before this rule with a dataset-creating role (Honest Broker, extra Admins) are
  moved to Guest once their uploads are confirmed to work through the dataset jobs below.

## Per-dataset roles

| On the dataset | What it gives | Typical holder |
|---|---|---|
| **Owner** | The dataset creator: all dataset operations | ARGO admin, always |
| **Dataset Access Manager** | Approves read-only users' requests to view or download; copies slides out of the dataset. Only Admin, Institutional Admin, PI or Honest Broker accounts | ARGO admin (no other eligible role is given out) |
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
| ARGO admin | Admin | Owner + Dataset Access Manager; builds the annotation project and eCRF; copies slides |
| PI | Guest | Approved; gets results as the admin's export |
| PM / coordinator | Guest | Approved + Metadata Entry Specialist + Data Contributor |
| RA who uploads | Guest | Data Contributor (+ Metadata Entry Specialist if they keep metadata) |
| Reader | Guest | Approved; assigned to the annotation project; stain and slide type only; no annotation review |
| Viewer | Guest | Read-Only |

Someone without a PathPresenter account is requested on the Study Personnel Request (platform:
PathPresenter); the ARGO admin creates it with the account role above.

## Pending: dataset creation for Admin only

Asked of PathPresenter on 2026-11-19: can dataset creation be turned off for every account role
but Admin on both portals (argo-ccr and argo-research)? Their access-control team is checking.
No role today lets a PM copy slides and manage people without also creating datasets.

**If they turn it off**, PMs and PIs move up, and every existing dataset is re-set to match:

| Person | Account role | On their study's dataset |
|---|---|---|
| PM | Principal Investigator | Dataset Access Manager + Metadata Entry Specialist + Data Contributor; Additional Project Owner on the annotation project. A PI can't delete a dataset it doesn't own, so the admin's datasets stay safe |
| Study PI | Principal Investigator | Dataset Access Manager; Additional Project Owner; sees Results directly |
| RA, reader, viewer | Guest | Unchanged |

Then, on each portal, dataset by dataset:
1. Its current owner shares it with the ARGO admin as Dataset Access Manager, if the admin
   doesn't own it.
2. The people on it are set exactly as the table above and the "Who gets what" table.
3. Accounts that held a dataset-creating role only to work around this (Honest Broker, extra
   Admins) go to Guest or Principal Investigator by their job.

**If they can't**, the tables above stand: the ARGO admin copies slides and manages access, and
PMs stay Guest.

