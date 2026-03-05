from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class PawnContract(models.Model):
    _name = 'pawn.contract'
    _description = 'Pawn Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(default='New', required=True, copy=False, readonly=True, tracking=True)
    customer_id = fields.Many2one('res.partner', required=True, tracking=True, index=True)
    guarantor_id = fields.Many2one('res.partner', tracking=True)
    collateral_ids = fields.One2many('pawn.collateral', 'contract_id', string='Collaterals')
    rule_profile_id = fields.Many2one('pawn.rule.profile', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        required=True,
        readonly=True,
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', store=True, readonly=True
    )

    principal_amount = fields.Monetary(required=True, tracking=True)
    interest_rate = fields.Float(tracking=True)
    penalty_rate = fields.Float(tracking=True)
    appraised_value = fields.Monetary(compute='_compute_appraised_value', store=True, readonly=True)

    loan_date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    maturity_date = fields.Date(required=True, tracking=True)
    grace_days = fields.Integer(default=0)

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('approved', 'Approved'),
            ('active', 'Active'),
            ('overdue', 'Overdue'),
            ('renewed', 'Renewed'),
            ('redeemed', 'Redeemed'),
            ('forfeited', 'Forfeited'),
            ('closed', 'Closed'),
        ],
        default='draft',
        tracking=True,
        required=True,
        index=True,
    )

    payment_ids = fields.One2many('pawn.payment', 'contract_id', string='Payments')
    disbursement_move_id = fields.Many2one('account.move', readonly=True, copy=False)
    forfeit_move_id = fields.Many2one('account.move', readonly=True, copy=False)

    total_interest_due = fields.Monetary(compute='_compute_financials', currency_field='currency_id')
    total_paid_interest = fields.Monetary(compute='_compute_financials', currency_field='currency_id')
    outstanding_principal = fields.Monetary(compute='_compute_financials', currency_field='currency_id')
    penalty_amount = fields.Monetary(compute='_compute_penalty_amount', currency_field='currency_id')

    payment_count = fields.Integer(compute='_compute_counts')
    move_count = fields.Integer(compute='_compute_counts')
    collateral_count = fields.Integer(compute='_compute_counts')

    _check_principal_non_negative = models.Constraint(
        'CHECK(principal_amount >= 0)',
        'Principal must be non-negative.',
    )
    _check_grace_days_non_negative = models.Constraint(
        'CHECK(grace_days >= 0)',
        'Grace days must be non-negative.',
    )

    @api.depends('collateral_ids.estimated_value')
    def _compute_appraised_value(self):
        for contract in self:
            contract.appraised_value = sum(contract.collateral_ids.mapped('estimated_value'))

    @api.depends(
        'payment_ids.state',
        'payment_ids.amount',
        'payment_ids.payment_type',
        'principal_amount',
        'interest_rate',
        'rule_profile_id.interest_type',
        'loan_date',
        'maturity_date',
    )
    def _compute_financials(self):
        for contract in self:
            posted_payments = contract.payment_ids.filtered(lambda p: p.state == 'posted')
            interest_paid = sum(posted_payments.filtered(lambda p: p.payment_type == 'interest').mapped('amount'))
            principal_paid = sum(posted_payments.filtered(lambda p: p.payment_type == 'principal').mapped('amount'))

            total_interest = contract._compute_interest_amount()
            contract.total_paid_interest = interest_paid
            contract.total_interest_due = max(total_interest - interest_paid, 0.0)
            contract.outstanding_principal = max(contract.principal_amount - principal_paid, 0.0)

    def _compute_interest_amount(self):
        self.ensure_one()
        if not self.loan_date or not self.maturity_date or self.maturity_date < self.loan_date:
            return 0.0

        days = (self.maturity_date - self.loan_date).days
        profile_type = self.rule_profile_id.interest_type or 'flat'
        rate = (self.interest_rate or 0.0) / 100.0

        if profile_type == 'daily':
            return self.principal_amount * rate * max(days, 0)
        if profile_type == 'monthly':
            delta = relativedelta(self.maturity_date, self.loan_date)
            total_months = delta.years * 12 + delta.months + (1 if delta.days > 0 else 0)
            return self.principal_amount * rate * max(total_months, 1)
        return self.principal_amount * rate

    @api.depends(
        'state',
        'maturity_date',
        'grace_days',
        'penalty_rate',
        'principal_amount',
        'payment_ids.state',
        'payment_ids.payment_type',
        'payment_ids.amount',
        'outstanding_principal',
    )
    def _compute_penalty_amount(self):
        today = fields.Date.context_today(self)
        for contract in self:
            if contract.state not in ('active', 'renewed', 'overdue') or not contract.maturity_date:
                contract.penalty_amount = 0.0
                continue

            grace_date = contract.maturity_date + timedelta(days=contract.grace_days or 0)
            if today <= grace_date:
                contract.penalty_amount = 0.0
                continue

            overdue_days = (today - grace_date).days
            gross_penalty = contract.outstanding_principal * ((contract.penalty_rate or 0.0) / 100.0) * overdue_days
            posted_penalty = sum(
                contract.payment_ids.filtered(
                    lambda p: p.state == 'posted' and p.payment_type == 'penalty'
                ).mapped('amount')
            )
            contract.penalty_amount = max(gross_penalty - posted_penalty, 0.0)

    @api.depends('payment_ids', 'payment_ids.account_move_id', 'disbursement_move_id', 'forfeit_move_id', 'collateral_ids')
    def _compute_counts(self):
        for contract in self:
            contract.payment_count = len(contract.payment_ids)
            move_ids = set(contract.payment_ids.mapped('account_move_id').ids)
            if contract.disbursement_move_id:
                move_ids.add(contract.disbursement_move_id.id)
            if contract.forfeit_move_id:
                move_ids.add(contract.forfeit_move_id.id)
            contract.move_count = len(move_ids)
            contract.collateral_count = len(contract.collateral_ids)

    @api.onchange('rule_profile_id')
    def _onchange_rule_profile_id(self):
        for contract in self:
            if not contract.rule_profile_id:
                continue
            contract.interest_rate = contract.rule_profile_id.interest_rate
            contract.penalty_rate = contract.rule_profile_id.penalty_rate
            contract.grace_days = contract.rule_profile_id.grace_days
            if contract.appraised_value and contract.rule_profile_id.max_ltv:
                contract.principal_amount = contract.appraised_value * (contract.rule_profile_id.max_ltv / 100.0)

    @api.constrains('principal_amount', 'appraised_value', 'rule_profile_id')
    def _check_ltv(self):
        for contract in self:
            if not contract.rule_profile_id or not contract.appraised_value:
                continue
            max_allowed = contract.appraised_value * (contract.rule_profile_id.max_ltv / 100.0)
            if contract.principal_amount > max_allowed:
                raise UserError('Principal amount exceeds rule profile max LTV.')

    @api.constrains('loan_date', 'maturity_date')
    def _check_dates(self):
        for contract in self:
            if contract.loan_date and contract.maturity_date and contract.maturity_date < contract.loan_date:
                raise UserError('Maturity date cannot be before loan date.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('pawn.contract') or 'New'
        return super().create(vals_list)

    @api.model
    def _get_default_journal(self):
        journal_id = self.env['ir.config_parameter'].sudo().get_param('pawn_management.cash_journal_id')
        if journal_id:
            return self.env['account.journal'].browse(int(journal_id))
        return self.env['account.journal'].search(
            [('type', 'in', ['cash', 'bank']), ('company_id', '=', self.env.company.id)],
            limit=1,
        )

    def _get_config_accounts(self):
        params = self.env['ir.config_parameter'].sudo()
        mapping = {
            'receivable': 'pawn_management.receivable_account_id',
            'interest_income': 'pawn_management.interest_income_account_id',
            'penalty_income': 'pawn_management.penalty_income_account_id',
            'inventory': 'pawn_management.inventory_account_id',
        }
        accounts = {}
        for key, param_key in mapping.items():
            account_id = params.get_param(param_key)
            accounts[key] = self.env['account.account'].browse(int(account_id)) if account_id else False
        return accounts

    def _check_manager_rights(self):
        if not self.env.user.has_group('pawn_lending.group_pawn_manager'):
            raise AccessError('Only Pawn Managers can run this action.')

    def action_approve(self):
        self._check_manager_rights()
        for contract in self.filtered(lambda c: c.state == 'draft'):
            contract.state = 'approved'

    def action_disburse(self):
        self._check_manager_rights()
        for contract in self.filtered(lambda c: c.state == 'approved'):
            if not contract.collateral_ids:
                raise UserError('Add at least one collateral item before disbursement.')

            accounts = contract._get_config_accounts()
            if not accounts['receivable']:
                raise UserError('Configure Pawn Loan Receivable account in settings.')

            journal = contract._get_default_journal()
            if not journal or not journal.default_account_id:
                raise UserError('Configure a cash/bank journal with a default account in settings.')

            move = self.env['account.move'].create(
                {
                    'move_type': 'entry',
                    'date': contract.loan_date,
                    'journal_id': journal.id,
                    'ref': contract.name,
                    'line_ids': [
                        (0, 0, {
                            'name': contract.name,
                            'partner_id': contract.customer_id.id,
                            'account_id': accounts['receivable'].id,
                            'debit': contract.principal_amount,
                            'credit': 0.0,
                        }),
                        (0, 0, {
                            'name': contract.name,
                            'partner_id': contract.customer_id.id,
                            'account_id': journal.default_account_id.id,
                            'debit': 0.0,
                            'credit': contract.principal_amount,
                        }),
                    ],
                }
            )
            move.action_post()
            contract.disbursement_move_id = move.id
            contract.collateral_ids.action_move_to_vault()
            contract.state = 'active'

    def action_mark_overdue(self):
        today = fields.Date.context_today(self)
        for contract in self.filtered(lambda c: c.state in ('active', 'renewed')):
            grace_date = contract.maturity_date + timedelta(days=contract.grace_days or 0)
            if today > grace_date:
                contract.state = 'overdue'

    def action_renew(self):
        self._check_manager_rights()
        for contract in self.filtered(lambda c: c.state in ('active', 'overdue')):
            contract.maturity_date = (contract.maturity_date or fields.Date.context_today(self)) + relativedelta(months=1)
            contract.state = 'renewed'

    def action_redeem(self):
        self._check_manager_rights()
        for contract in self.filtered(lambda c: c.state in ('active', 'renewed', 'overdue')):
            if contract.outstanding_principal > 0.0:
                raise UserError('Outstanding principal must be fully paid before redemption.')
            if contract.total_interest_due > 0.0:
                raise UserError('Outstanding interest must be fully paid before redemption.')
            if contract.penalty_amount > 0.0:
                raise UserError('Outstanding penalty must be fully paid before redemption.')
            contract.collateral_ids.action_return_to_customer()
            contract.state = 'redeemed'

    def action_forfeit(self):
        self._check_manager_rights()
        for contract in self.filtered(lambda c: c.state in ('active', 'renewed', 'overdue')):
            accounts = contract._get_config_accounts()
            if not accounts['inventory'] or not accounts['receivable']:
                raise UserError('Configure Inventory and Pawn Loan Receivable accounts in settings.')

            journal = contract._get_default_journal()
            if not journal:
                raise UserError('Configure default cash/bank journal in settings.')

            contract.collateral_ids.action_move_to_vault()
            amount = contract.outstanding_principal
            if amount > 0.0:
                move = self.env['account.move'].create(
                    {
                        'move_type': 'entry',
                        'date': fields.Date.context_today(self),
                        'journal_id': journal.id,
                        'ref': f'{contract.name} - Forfeit',
                        'line_ids': [
                            (0, 0, {
                                'name': contract.name,
                                'partner_id': contract.customer_id.id,
                                'account_id': accounts['inventory'].id,
                                'debit': amount,
                                'credit': 0.0,
                            }),
                            (0, 0, {
                                'name': contract.name,
                                'partner_id': contract.customer_id.id,
                                'account_id': accounts['receivable'].id,
                                'debit': 0.0,
                                'credit': amount,
                            }),
                        ],
                    }
                )
                move.action_post()
                contract.forfeit_move_id = move.id
            contract.state = 'forfeited'

    def action_close(self):
        self._check_manager_rights()
        for contract in self.filtered(lambda c: c.state in ('redeemed', 'forfeited')):
            contract.state = 'closed'

    def action_view_payments(self):
        self.ensure_one()
        action = self.env.ref('pawn_lending.action_pawn_payment').read()[0]
        action['domain'] = [('contract_id', '=', self.id)]
        action['context'] = {'default_contract_id': self.id}
        return action

    def action_view_moves(self):
        self.ensure_one()
        move_ids = set(self.payment_ids.mapped('account_move_id').ids)
        if self.disbursement_move_id:
            move_ids.add(self.disbursement_move_id.id)
        if self.forfeit_move_id:
            move_ids.add(self.forfeit_move_id.id)

        action = self.env.ref('account.action_move_journal_line').read()[0]
        action['domain'] = [('id', 'in', list(move_ids))]
        return action

    def action_view_collateral(self):
        self.ensure_one()
        action = self.env.ref('pawn_lending.action_pawn_collateral').read()[0]
        action['domain'] = [('contract_id', '=', self.id)]
        action['context'] = {'default_contract_id': self.id}
        return action

    def action_print_ticket(self):
        self.ensure_one()
        return self.env.ref('pawn_lending.action_report_pawn_ticket').report_action(self)

    def action_print_redemption_receipt(self):
        self.ensure_one()
        return self.env.ref('pawn_lending.action_report_redemption_receipt').report_action(self)

    @api.model
    def _cron_mark_overdue(self):
        today = fields.Date.context_today(self)
        contracts = self.search([
            ('state', 'in', ['active', 'renewed']),
            ('maturity_date', '!=', False),
        ])
        for contract in contracts:
            grace_date = contract.maturity_date + timedelta(days=contract.grace_days or 0)
            if today > grace_date:
                contract.state = 'overdue'
