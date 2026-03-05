/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

class PawnDashboardAction extends Component {
    static template = "pawn_lending.PawnDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        const now = new Date();
        const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
        const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0);

        const formatDate = (d) => {
            const yyyy = d.getFullYear();
            const mm = String(d.getMonth() + 1).padStart(2, '0');
            const dd = String(d.getDate()).padStart(2, '0');
            return `${yyyy}-${mm}-${dd}`;
        };

        this.state = useState({
            loading: true,
            revenuePeriod: "6m",
            transactionPeriod: "week",
            dateFrom: formatDate(firstDay),
            dateTo: formatDate(lastDay),
            data: null,
        });

        onWillStart(async () => {
            await this._load();
        });
    }

    async _load() {
        this.state.loading = true;
        this.state.data = await this.orm.call(
            "pawn.dashboard",
            "get_dashboard_data",
            [
                this.state.revenuePeriod,
                this.state.transactionPeriod,
                this.state.dateFrom || false,
                this.state.dateTo || false,
            ]
        );
        this.state.loading = false;
    }

    async onChangeRevenuePeriod(ev) {
        this.state.revenuePeriod = ev.target.value;
        await this._load();
    }

    async onChangeTransactionPeriod(ev) {
        this.state.transactionPeriod = ev.target.value;
        await this._load();
    }

    onChangeDateFrom(ev) {
        this.state.dateFrom = ev.target.value;
    }

    onChangeDateTo(ev) {
        this.state.dateTo = ev.target.value;
    }

    async applyFilter() {
        await this._load();
    }

    async clearFilter() {
        const now = new Date();
        const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
        const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0);

        const formatDate = (d) => {
            const yyyy = d.getFullYear();
            const mm = String(d.getMonth() + 1).padStart(2, '0');
            const dd = String(d.getDate()).padStart(2, '0');
            return `${yyyy}-${mm}-${dd}`;
        };

        this.state.dateFrom = formatDate(firstDay);
        this.state.dateTo = formatDate(lastDay);
        await this._load();
    }

    get statusRows() {
        if (!this.state.data) {
            return [];
        }
        const entries = Object.entries(this.state.data.status_distribution);
        const total = entries.reduce((sum, [, val]) => sum + val, 0) || 1;
        const colors = {
            Active: "#1e8e3e",
            Overdue: "#f89c1e",
            Forfeited: "#c5221f",
            Redeemed: "#008394",
        };
        return entries.map(([label, value]) => ({
            label,
            value,
            color: colors[label] || "#888",
            pct: Math.round((value / total) * 100),
        }));
    }

    get statusConicStyle() {
        const rows = this.statusRows;
        const total = rows.reduce((s, r) => s + r.value, 0);
        if (!rows.length || !total) {
            return "background: conic-gradient(#f1f3f5 0 100%);";
        }
        let start = 0;
        const stops = rows.map((r) => {
            const end = start + r.pct;
            const s = `${r.color} ${start}% ${end}%`;
            start = end;
            return s;
        });
        return `background: conic-gradient(${stops.join(",")});`;
    }

    get collateralRows() {
        if (!this.state.data) {
            return [];
        }
        const entries = Object.entries(this.state.data.collateral_categories);
        const max = Math.max(...entries.map(([, val]) => val), 1);
        const colors = ["#00a09d", "#1967d2", "#6610f2", "#d63384", "#fd7e14", "#20c997"];
        return entries.map(([label, value], idx) => ({
            label,
            value,
            width: Math.round((value / max) * 100),
            color: colors[idx % colors.length],
        }));
    }

    get _revenueNiceMax() {
        const vals = [
            ...(this.state.data?.monthly_revenue?.interest || []),
            ...(this.state.data?.monthly_revenue?.penalties || []),
        ];
        return this._niceMax(Math.max(...vals, 0), 6);
    }

    get revenueChartPointsInterest() {
        return this._toPolyline(this.state.data?.monthly_revenue?.interest || [], this._revenueNiceMax);
    }

    get revenueChartPointsPenalties() {
        return this._toPolyline(this.state.data?.monthly_revenue?.penalties || [], this._revenueNiceMax);
    }

    _toPolyline(values, scaleMax) {
        if (!values.length) {
            return "";
        }
        const max = scaleMax || Math.max(...values, 1);
        const w = 520;
        const h = 180;
        const gap = values.length > 1 ? w / (values.length - 1) : w;
        return values
            .map((v, i) => {
                const x = Math.round(i * gap);
                const y = Math.round(h - (v / max) * h);
                return `${x},${y}`;
            })
            .join(" ");
    }

    get dailyRows() {
        if (!this.state.data) {
            return [];
        }
        const labels = this.state.data.daily_transactions.labels;
        const loans = this.state.data.daily_transactions.new_loans;
        const repays = this.state.data.daily_transactions.repayments;
        const nice = this._niceMax(Math.max(...loans, ...repays, 0), 5);
        const max = nice || 1;
        return labels.map((label, i) => ({
            label,
            loans: loans[i],
            repayments: repays[i],
            loansHeight: Math.round((loans[i] / max) * 100),
            repaysHeight: Math.round((repays[i] / max) * 100),
        }));
    }

    get revenueYLabels() {
        return this._yLabelsFromNice(this._revenueNiceMax, 6);
    }

    get dailyYLabels() {
        if (!this.state.data) return [];
        const { new_loans, repayments } = this.state.data.daily_transactions;
        const nice = this._niceMax(Math.max(...(new_loans || [0]), ...(repayments || [0])), 5);
        return this._yLabelsFromNice(nice, 5);
    }

    _yLabelsFromNice(nice, steps) {
        return Array.from({ length: steps + 1 }, (_, i) => {
            const val = Math.round((nice / steps) * (steps - i));
            return { val, label: val.toLocaleString() };
        });
    }

    _niceMax(max, steps) {
        if (!max) return steps;
        const rough = max / steps;
        const mag = Math.pow(10, Math.floor(Math.log10(rough)));
        const unit = Math.ceil(rough / mag) * mag;
        // Ensure the nice max is at least `steps` so each step is a whole integer
        return Math.max(unit * steps, steps);
    }

    capitalize(str) {
        return str ? str.charAt(0).toUpperCase() + str.slice(1) : '';
    }

    fmtSign(val) {
        const n = Number(val || 0);
        return (n > 0 ? '+' : '') + n;
    }

    statusClass(status) {
        return `status-pill status-${status}`;
    }

    async openContract(contractId) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "pawn.contract",
            views: [[false, "form"]],
            res_id: contractId,
            target: "current",
        });
    }

    async openAllContracts() {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "All Contracts",
            res_model: "pawn.contract",
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

    async openDueToday() {
        const today = new Date();
        const yyyy = today.getFullYear();
        const mm = String(today.getMonth() + 1).padStart(2, '0');
        const dd = String(today.getDate()).padStart(2, '0');
        const todayStr = `${yyyy}-${mm}-${dd}`;
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Due Today",
            res_model: "pawn.contract",
            views: [[false, "list"], [false, "form"]],
            domain: [["maturity_date", "=", todayStr], ["state", "in", ["active", "renewed"]]],
            target: "current",
        });
    }

    async openLateCustomers() {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Late Customers",
            res_model: "pawn.contract",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "=", "overdue"]],
            target: "current",
        });
    }

    fmtMoney(value) {
        const symbol = this.state.data?.currency_symbol || "$";
        const num = Number(value || 0);
        return `${symbol}${num.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
    }
}

registry.category("actions").add("pawn_dashboard", PawnDashboardAction);
