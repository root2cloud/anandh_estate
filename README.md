# Real Estate Management

An advanced, professional real estate management platform built as an Odoo
application (Odoo 17/18). It combines a branded public website with a full
back-office for managing properties, agents and customers.

## Highlights

- **Branded website header** — logo (top-left) + "Real Estate Management"
  brand name + navigation: Home, Properties, Customer Registration,
  Agent Registration, Customer Dashboard, Agent Dashboard, and a
  "List Your Property" call-to-action. Used consistently across every page.
- **Property listings** with an interactive map, search/filter, categories
  (Residential, Commercial, Agricultural, ...) and rich detail pages.
- **Customer registration workflow**
  1. A visitor fills the public form at `/customer/register`.
  2. The request lands in **Real Estate Management → Customer Registrations**
     for admin review.
  3. On **Approve**, a customer profile is created and a portal login is
     automatically provisioned (the customer receives access to
     `/my/customer/dashboard`). The approved profile also appears under
     **Real Estate Management → Customers**.
  4. On **Reject**, the admin records a rejection reason via a confirmation
     wizard.
- **Agent registration workflow** — same approve/reject pattern, creating an
  agent profile, portal login and access to `/my/agent/dashboard`.
- **Property submissions** — customers can also submit a property they want
  listed (`/property/register`); approved submissions become live
  `property.property` records.

## Backend menu structure

```
Real Estate Management
├── Properties
├── Property Submissions        (property.registration — "I want to sell/list this")
├── Property Categories         (Residential, Commercial, Agricultural, ...)
├── Customer Registrations      (customer.registration — approve → Customers)
├── Agent Registrations         (agent.registration — approve → Agents)
├── Customers                   (approved customer profiles, portal-enabled)
└── Agents                      (approved agent profiles, portal-enabled)
```

## Key routes

| Route | Purpose |
|---|---|
| `/` | Property map / homepage |
| `/properties` | Property listing & search |
| `/property/<id>` | Property detail page |
| `/property/register` | Submit a property for listing |
| `/customer/register` | Customer sign-up form |
| `/agent/register` | Agent sign-up form |
| `/my/customer/dashboard` | Customer portal dashboard (requires approved login) |
| `/my/agent/dashboard` | Agent portal dashboard (requires approved login) |

## Notes for further customization

This module is built to be extended — new fields on the registration forms,
extra backend menus, or additional dashboard widgets can be added without
restructuring what's here. Let the team know what you'd like added next
(e.g. property favorites/wishlists for customers, lead assignment to agents,
SMS/WhatsApp notifications, payment integration, etc.).

## Installation

1. Copy the `real_estate_management` folder into your Odoo `addons` path.
2. Restart the Odoo server and update the apps list.
3. Install **Real Estate Management** from the Apps menu.
4. Configure company details, then visit the website to see the branded
   header and try the registration flows end-to-end.
