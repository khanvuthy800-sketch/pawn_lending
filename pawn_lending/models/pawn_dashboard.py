from collections import defaultdict
from datetime import date, timedelta

from odoo import api, fields, models


class PawnDashboard(models.TransientModel):
    _name = 'pawn.dashboard'
    _description = 'Pawn Management Dashboard'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    date_from = fields.Date(default=lambda self: fields.Date.to_string(date.today().replace(day=1)))
    date_to = fields.Date(default=fields.Date.context_today)

    total_contracts = fields.Integer(compute='_compute_kpis')
    active_contracts = fields.Integer(compute='_compute_kpis')
    overdue_contracts = fields.Integer(compute='_compute_kpis')
    forfeited_contracts = fields.Integer(compute='_compute_kpis')

    total_principal_disbursed = fields.Monetary(currency_field='currency_id', compute='_compute_kpis')
    total_outstanding_principal = fields.Monetary(currency_field='currency_id', compute='_compute_kpis')
    total_interest_collected = fields.Monetary(currency_field='currency_id', compute='_compute_kpis')
    total_penalty_collected = fields.Monetary(currency_field='currency_id', compute='_compute_kpis')
    total_collection = fields.Monetary(currency_field='currency_id', compute='_compute_kpis')

    def _get_contract_domain(self, states=None):
        self.ensure_one()
        domain = [('company_id', '=', self.company_id.id)]
        if self.date_from:
            domain.append(('loan_date', '>=', self.date_from))
        if self.date_to:
            domain.append(('loan_date', '<=', self.date_to))
        if states:
            domain.append(('state', 'in', states))
        return domain

    def _get_payment_domain(self, payment_types=None):
        self.ensure_one()
        domain = [
            ('state', '=', 'posted'),
            ('contract_id.company_id', '=', self.company_id.id),
        ]
        if self.date_from:
            domain.append(('payment_date', '>=', self.date_from))
        if self.date_to:
            domain.append(('payment_date', '<=', self.date_to))
        if payment_types:
            domain.append(('payment_type', 'in', payment_types))
        return domain

    @api.depends('date_from', 'date_to', 'company_id')
    def _compute_kpis(self):
        Contract = self.env['pawn.contract'].sudo()
        Payment = self.env['pawn.payment'].sudo()

        for dashboard in self:
            base_contract_domain = dashboard._get_contract_domain()
            dashboard.total_contracts = Contract.search_count(base_contract_domain)
            dashboard.active_contracts = Contract.search_count(
                dashboard._get_contract_domain(states=['active', 'renewed'])
            )
            dashboard.overdue_contracts = Contract.search_count(
                dashboard._get_contract_domain(states=['overdue'])
            )
            dashboard.forfeited_contracts = Contract.search_count(
                dashboard._get_contract_domain(states=['forfeited'])
            )

            disbursed_states = ['approved', 'active', 'overdue', 'renewed', 'redeemed', 'forfeited', 'closed']
            disbursed_contracts = Contract.search(dashboard._get_contract_domain(states=disbursed_states))
            dashboard.total_principal_disbursed = sum(disbursed_contracts.mapped('principal_amount'))

            outstanding_contracts = Contract.search(
                dashboard._get_contract_domain(states=['active', 'overdue', 'renewed'])
            )
            dashboard.total_outstanding_principal = sum(outstanding_contracts.mapped('outstanding_principal'))

            interest_paid = Payment.search(dashboard._get_payment_domain(payment_types=['interest']))
            penalty_paid = Payment.search(dashboard._get_payment_domain(payment_types=['penalty']))
            all_paid = Payment.search(
                dashboard._get_payment_domain(payment_types=['interest', 'penalty', 'principal'])
            )
            dashboard.total_interest_collected = sum(interest_paid.mapped('amount'))
            dashboard.total_penalty_collected = sum(penalty_paid.mapped('amount'))
            dashboard.total_collection = sum(all_paid.mapped('amount'))

    def action_refresh(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pawn Dashboard',
            'res_model': 'pawn.dashboard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def _open_contract_action(self, states=None):
        self.ensure_one()
        action = self.env.ref('pawn_lending.action_pawn_contract').read()[0]
        action['domain'] = self._get_contract_domain(states=states)
        return action

    def action_open_contracts(self):
        return self._open_contract_action(states=None)

    def action_open_active_contracts(self):
        return self._open_contract_action(states=['active', 'renewed'])

    def action_open_overdue_contracts(self):
        return self._open_contract_action(states=['overdue'])

    def action_open_forfeited_contracts(self):
        return self._open_contract_action(states=['forfeited'])

    def action_open_payments(self):
        self.ensure_one()
        action = self.env.ref('pawn_lending.action_pawn_payment').read()[0]
        action['domain'] = self._get_payment_domain(payment_types=['interest', 'penalty', 'principal'])
        return action

    @api.model
    def get_dashboard_data(self, revenue_period='6m', transaction_period='week', date_from=False, date_to=False):
        company = self.env.company
        Contract = self.env['pawn.contract'].sudo()
        Payment = self.env['pawn.payment'].sudo()

        def _month_start(d):
            return d.replace(day=1)

        def _shift_month(d, delta):
            y = d.year + (d.month - 1 + delta) // 12
            m = (d.month - 1 + delta) % 12 + 1
            return d.replace(year=y, month=m, day=1)

        today = fields.Date.context_today(self)

        if date_from and isinstance(date_from, str):
            date_from = fields.Date.from_string(date_from)
        if date_to and isinstance(date_to, str):
            date_to = fields.Date.from_string(date_to)

        eff_to = date_to or today

        # Base domain helpers applying the date range filter
        def _contract_domain(extra=None):
            d = [('company_id', '=', company.id)]
            if date_from:
                d.append(('loan_date', '>=', date_from))
            if date_to:
                d.append(('loan_date', '<=', date_to))
            return d + (extra or [])

        def _payment_domain(extra=None):
            d = [('state', '=', 'posted'), ('contract_id.company_id', '=', company.id)]
            if date_from:
                d.append(('payment_date', '>=', date_from))
            if date_to:
                d.append(('payment_date', '<=', date_to))
            return d + (extra or [])

        # ── Monthly Revenue ───────────────────────────────────────────────────
        if date_from:
            rev_start = _month_start(date_from)
            rev_end = eff_to
            month_labels = []
            cur = rev_start
            while cur <= _month_start(rev_end):
                month_labels.append(cur.strftime('%b'))
                cur = _shift_month(cur, 1)
            # cap at 24 months
            if len(month_labels) > 24:
                month_labels = month_labels[-24:]
                rev_start = _month_start(_shift_month(_month_start(rev_end), -23))
            month_count = len(month_labels)
            start_month = rev_start
        else:
            months_map = {'3m': 3, '6m': 6, '12m': 12}
            month_count = months_map.get(revenue_period, 6)
            start_month = _month_start(_shift_month(eff_to, -(month_count - 1)))
            month_labels = []

        p_domain = [
            ('state', '=', 'posted'),
            ('contract_id.company_id', '=', company.id),
            ('payment_date', '>=', start_month),
            ('payment_date', '<=', eff_to),
        ]
        payments = Payment.search(p_domain)
        grouped = defaultdict(lambda: {'interest': 0.0, 'penalty': 0.0})
        for p in payments:
            if not p.payment_date:
                continue
            key = p.payment_date.strftime('%Y-%m')
            if p.payment_type == 'interest':
                grouped[key]['interest'] += p.amount
            elif p.payment_type == 'penalty':
                grouped[key]['penalty'] += p.amount

        interest_by_month = []
        penalty_by_month = []
        current = start_month
        for _i in range(month_count):
            key = current.strftime('%Y-%m')
            if not date_from:
                month_labels.append(current.strftime('%b'))
            interest_by_month.append(round(grouped[key]['interest'], 2))
            penalty_by_month.append(round(grouped[key]['penalty'], 2))
            current = _shift_month(current, 1)

        # ── Status Distribution ───────────────────────────────────────────────
        status_states = ['active', 'overdue', 'forfeited', 'redeemed']
        status_counts = {
            'Active': Contract.search_count(_contract_domain([('state', '=', 'active')])),
            'Overdue': Contract.search_count(_contract_domain([('state', '=', 'overdue')])),
            'Forfeited': Contract.search_count(_contract_domain([('state', '=', 'forfeited')])),
            'Redeemed': Contract.search_count(_contract_domain([('state', '=', 'redeemed')])),
        }

        # ── Collateral Categories ─────────────────────────────────────────────
        coll_domain = [('contract_id.company_id', '=', company.id)]
        if date_from:
            coll_domain.append(('contract_id.loan_date', '>=', date_from))
        if date_to:
            coll_domain.append(('contract_id.loan_date', '<=', date_to))
        collaterals = self.env['pawn.collateral'].sudo().search(coll_domain)
        category_labels = {
            'gold': 'Jewelry',
            'phone': 'Electronics',
            'motorbike': 'Vehicles',
            'other': 'Others',
        }
        category_counts = defaultdict(int)
        for col in collaterals:
            category_counts[category_labels.get(col.category, 'Others')] += 1

        # ── Daily Transactions ────────────────────────────────────────────────
        if date_from:
            daily_end = eff_to
            daily_start = max(date_from, eff_to - timedelta(days=29))
        else:
            days = 30 if transaction_period == 'month' else 7
            daily_end = today
            daily_start = today - timedelta(days=days - 1)

        loan_domain = [
            ('company_id', '=', company.id),
            ('loan_date', '>=', daily_start),
            ('loan_date', '<=', daily_end),
        ]
        repay_domain = [
            ('state', '=', 'posted'),
            ('contract_id.company_id', '=', company.id),
            ('payment_type', '=', 'principal'),
            ('payment_date', '>=', daily_start),
            ('payment_date', '<=', daily_end),
        ]
        loans = Contract.search(loan_domain)
        repays = Payment.search(repay_domain)

        loans_by_day = defaultdict(int)
        repays_by_day = defaultdict(int)
        for c in loans:
            if c.loan_date:
                loans_by_day[c.loan_date] += 1
        for p in repays:
            if p.payment_date:
                repays_by_day[p.payment_date] += 1

        day_labels = []
        day_new_loans = []
        day_repayments = []
        d = daily_start
        while d <= daily_end:
            day_labels.append(d.strftime('%a'))
            day_new_loans.append(loans_by_day[d])
            day_repayments.append(repays_by_day[d])
            d += timedelta(days=1)

        # ── Recent Contracts ──────────────────────────────────────────────────
        recent_contracts = Contract.search(_contract_domain(), order='id desc', limit=6)
        recent_rows = []
        for c in recent_contracts:
            recent_rows.append({
                'id': c.id,
                'contract': c.name,
                'customer': c.customer_id.display_name,
                'collateral': c.collateral_ids[:1].name if c.collateral_ids else '-',
                'principal': c.principal_amount,
                'interest_rate': c.interest_rate,
                'due_date': c.maturity_date and c.maturity_date.strftime('%Y-%m-%d') or '-',
                'status': c.state,
            })

        # ── Due Today ─────────────────────────────────────────────────────────
        due_today_contracts = Contract.search([
            ('company_id', '=', company.id),
            ('maturity_date', '=', today),
            ('state', 'in', ['active', 'renewed']),
        ], order='id desc')
        due_today_rows = []
        for c in due_today_contracts:
            due_today_rows.append({
                'id': c.id,
                'contract': c.name,
                'customer': c.customer_id.display_name,
                'principal': c.principal_amount,
                'outstanding_principal': c.outstanding_principal,
                'total_interest_due': c.total_interest_due,
                'due_date': c.maturity_date.strftime('%Y-%m-%d'),
                'status': c.state,
            })

        # ── Late Customers ────────────────────────────────────────────────────
        late_contracts = Contract.search([
            ('company_id', '=', company.id),
            ('state', '=', 'overdue'),
        ], order='maturity_date asc')
        late_rows = []
        for c in late_contracts:
            overdue_days = (today - c.maturity_date).days if c.maturity_date else 0
            late_rows.append({
                'id': c.id,
                'contract': c.name,
                'customer': c.customer_id.display_name,
                'principal': c.principal_amount,
                'outstanding_principal': c.outstanding_principal,
                'penalty_amount': c.penalty_amount,
                'due_date': c.maturity_date and c.maturity_date.strftime('%Y-%m-%d') or '-',
                'overdue_days': overdue_days,
                'status': c.state,
            })

        # ── Operational Metrics ───────────────────────────────────────────────
        total_contracts = Contract.search_count(_contract_domain())
        total_forfeited = Contract.search_count(_contract_domain([('state', '=', 'forfeited')]))
        forfeit_rate = round((total_forfeited / total_contracts) * 100, 2) if total_contracts else 0.0

        customers = Contract.search(_contract_domain()).mapped('customer_id').ids
        total_customers = len(set(customers))

        contract_durations = []
        for c in Contract.search(_contract_domain([('loan_date', '!=', False), ('maturity_date', '!=', False)])):
            if c.maturity_date >= c.loan_date:
                contract_durations.append((c.maturity_date - c.loan_date).days)
        avg_duration = round(sum(contract_durations) / len(contract_durations), 1) if contract_durations else 0.0

        inv_coll_domain = [
            ('contract_id.company_id', '=', company.id),
            ('contract_id.state', '=', 'forfeited'),
        ]
        if date_from:
            inv_coll_domain.append(('contract_id.loan_date', '>=', date_from))
        if date_to:
            inv_coll_domain.append(('contract_id.loan_date', '<=', date_to))
        inventory_value = sum(
            self.env['pawn.collateral'].sudo().search(inv_coll_domain).mapped('estimated_value')
        )

        now_month_start = _month_start(eff_to)
        prev_month_start = _shift_month(now_month_start, -1)
        prev_month_end = now_month_start - timedelta(days=1)

        current_month_customers = set(Contract.search([
            ('company_id', '=', company.id),
            ('loan_date', '>=', now_month_start),
            ('loan_date', '<=', eff_to),
        ]).mapped('customer_id').ids)
        prev_month_customers = set(Contract.search([
            ('company_id', '=', company.id),
            ('loan_date', '>=', prev_month_start),
            ('loan_date', '<=', prev_month_end),
        ]).mapped('customer_id').ids)
        new_customers_this_month = len(current_month_customers - prev_month_customers)

        prev_inv_domain = [
            ('contract_id.company_id', '=', company.id),
            ('contract_id.state', '=', 'forfeited'),
            ('contract_id.loan_date', '<', now_month_start),
        ]
        if date_from:
            prev_inv_domain.append(('contract_id.loan_date', '>=', date_from))
        prev_inventory = sum(
            self.env['pawn.collateral'].sudo().search(prev_inv_domain).mapped('estimated_value')
        )
        inv_change = round(((inventory_value - prev_inventory) / prev_inventory) * 100, 2) if prev_inventory else 0.0

        prev_base = [('company_id', '=', company.id), ('loan_date', '<', now_month_start)]
        if date_from:
            prev_base.append(('loan_date', '>=', date_from))
        prev_total = Contract.search_count(prev_base)
        prev_forfeit = Contract.search_count(prev_base + [('state', '=', 'forfeited')])
        prev_forfeit_rate = round((prev_forfeit / prev_total) * 100, 2) if prev_total else 0.0

        return {
            'currency_symbol': company.currency_id.symbol,
            'monthly_revenue': {
                'labels': month_labels,
                'interest': interest_by_month,
                'penalties': penalty_by_month,
            },
            'status_distribution': status_counts,
            'collateral_categories': dict(sorted(category_counts.items(), key=lambda x: x[1], reverse=True)),
            'daily_transactions': {
                'labels': day_labels,
                'new_loans': day_new_loans,
                'repayments': day_repayments,
            },
            'recent_contracts': recent_rows,
            'due_today': due_today_rows,
            'late_customers': late_rows,
            'operational_metrics': {
                'total_customers': total_customers,
                'new_customers_this_month': new_customers_this_month,
                'average_contract_duration': avg_duration,
                'inventory_value': round(inventory_value, 2),
                'inventory_change_pct': inv_change,
                'forfeit_rate': forfeit_rate,
                'forfeit_rate_change': round(forfeit_rate - prev_forfeit_rate, 2),
            },
            'states': status_states,
        }
