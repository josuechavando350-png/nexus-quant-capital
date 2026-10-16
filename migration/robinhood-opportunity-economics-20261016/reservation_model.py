#!/usr/bin/env python3
"""OFFLINE paper ledger for a finite, prepaid ETH research budget.

It reserves the full prefund BEFORE an authorization would be issued. Pending
requests count, and settlement/timeout never replenishes this lifetime budget.
No signatures, RPC calls, invoices, revenue conversion or real-money control.
Production would need authenticated funding, finality/reorg reconciliation,
contract enforcement and independently agreed non-recourse commercial terms.
"""
import sqlite3


class PaperBudget:
    def __init__(self, path, hypothetical_funded_wei):
        if type(hypothetical_funded_wei) is not int or not 0 <= hypothetical_funded_wei < 2**63:
            raise ValueError('bounded nonnegative hypothetical capital required')
        self.path = str(path)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY CHECK(id=1), funded INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS reservations (op TEXT PRIMARY KEY, nonce_key TEXT UNIQUE NOT NULL, cap INTEGER NOT NULL, actual INTEGER, receipt TEXT)')
            db.execute('INSERT OR IGNORE INTO budget VALUES(1, ?)', (hypothetical_funded_wei,))
            if db.execute('SELECT funded FROM budget').fetchone()[0] != hypothetical_funded_wei:
                raise ValueError('cannot reset or refill the paper budget')

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def reserve(self, op, nonce_key, max_cost_wei):
        if not op or not nonce_key or type(max_cost_wei) is not int or not 0 < max_cost_wei < 2**63:
            raise ValueError('identity and positive full prefund required')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT nonce_key, cap FROM reservations WHERE op=?', (op,)).fetchone()
            if prior:
                if prior != (nonce_key, max_cost_wei):
                    raise ValueError('operation identity reused with different commitment')
                return False  # Idempotent replay, no new grant.
            available = db.execute('SELECT funded-(SELECT COALESCE(SUM(cap),0) FROM reservations) FROM budget').fetchone()[0]
            if max_cost_wei > available:
                raise ValueError('no prepaid capacity')
            try:
                db.execute('INSERT INTO reservations(op, nonce_key, cap) VALUES(?,?,?)', (op, nonce_key, max_cost_wei))
            except sqlite3.IntegrityError as error:
                raise ValueError('nonce already reserved') from error
            return True

    def reconcile(self, op, actual_wei, receipt_identity):
        if type(actual_wei) is not int or actual_wei < 0 or not receipt_identity:
            raise ValueError('nonnegative observed charge and evidence identity required')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT cap, actual, receipt FROM reservations WHERE op=?', (op,)).fetchone()
            if prior is None or actual_wei > prior[0]:
                raise ValueError('unreserved or over-cap charge; investigation required')
            if prior[1] is not None and prior[1:] != (actual_wei, receipt_identity):
                raise ValueError('conflicting reconciliation')
            db.execute('UPDATE reservations SET actual=?, receipt=? WHERE op=?', (actual_wei, receipt_identity, op))
            # No reservation release: current fixture validation has no expiry.

    def snapshot(self):
        with self.connect() as db:
            funded = db.execute('SELECT funded FROM budget').fetchone()[0]
            count, reserved, actual = db.execute('SELECT COUNT(*),COALESCE(SUM(cap),0),COALESCE(SUM(actual),0) FROM reservations').fetchone()
        return dict(hypothetical_funded_wei=funded, lifetime_reserved_wei=reserved,
                    remaining_wei=funded-reserved, recorded_actual_wei=actual,
                    reservations=count, production_enforcement=False)
