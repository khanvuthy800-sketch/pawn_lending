from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pawn_receivable_account_id = fields.Many2one(
        'account.account',
        string='Pawn Loan Receivable Account',
        config_parameter='pawn_management.receivable_account_id',
        domain=[('active', '=', True), ('account_type', '=', 'asset_receivable')],
        help="Account used to track the outstanding loan principal owed by customers. Debited on disbursement, credited on principal payment.",
    )
    pawn_interest_income_account_id = fields.Many2one(
        'account.account',
        string='Interest Income Account',
        config_parameter='pawn_management.interest_income_account_id',
        domain=[('active', '=', True), ('account_type', 'in', ['income', 'income_other'])],
        help="Account used to record revenue generated from interest payments.",
    )
    pawn_penalty_income_account_id = fields.Many2one(
        'account.account',
        string='Penalty Income Account',
        config_parameter='pawn_management.penalty_income_account_id',
        domain=[('active', '=', True), ('account_type', 'in', ['income', 'income_other'])],
        help="Account used to record revenue generated from late payment penalties.",
    )
    pawn_profit_account_id = fields.Many2one(
        'account.account',
        string='Pawn Profit Account',
        config_parameter='pawn_management.profit_account_id',
        domain=[('active', '=', True), ('account_type', 'in', ['income', 'income_other', 'expense_direct_cost'])],
        help="Account used to record the profit or loss when a forfeited item is sold.",
    )
    pawn_inventory_account_id = fields.Many2one(
        'account.account',
        string='Inventory Account',
        config_parameter='pawn_management.inventory_account_id',
        domain=[('active', '=', True), ('account_type', 'in', ['asset_current', 'asset_non_current'])],
        help="Account used to hold the value of forfeited items before they are sold.",
    )
    pawn_cash_journal_id = fields.Many2one(
        'account.journal',
        string='Default Cash/Bank Journal',
        config_parameter='pawn_management.cash_journal_id',
        domain=[('type', 'in', ['cash', 'bank'])],
        help="Default journal used for recording cash and bank payments.",
    )
