# ATLAS OS User Interface & Security System

This module provides the User Interface, authentication system, role-based access control, and auditing logging foundation for ATLAS OS.

## Features
- **Generic Biometric Boundary**: Abstract `FaceVerifier` interface to decouple core authorization from production CV algorithms.
- **Secure Password Storage**: Utilizes PBKDF2-HMAC-SHA256 with random salts and 100,000 iterations.
- **Role-Based Access Control (RBAC)**: Support for `ADMIN` and `USER` roles mapping to explicit permissions.
- **FastAPI Backend**: Fully independent API backend and session manager.
- **Futuristic Fronted UI**: HTML5 / CSS3 / Vanilla JS single page autonomous control dashboard served locally.
