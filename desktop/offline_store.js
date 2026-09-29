const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

function clone(value) {
    return JSON.parse(JSON.stringify(value));
}

function asNumber(value) {
    const parsed = Number(String(value ?? 0).replace(",", "."));
    return Number.isFinite(parsed) ? parsed : 0;
}

class DesktopOfflineStore {
    constructor(filePath) {
        this.filePath = filePath;
        this.data = { version: 1, activeIdentity: null, identities: {} };
        this.load();
    }

    load() {
        try {
            const raw = fs.readFileSync(this.filePath, "utf8");
            const parsed = JSON.parse(raw);
            if (parsed && typeof parsed === "object") {
                this.data = {
                    version: 1,
                    activeIdentity: parsed.activeIdentity || null,
                    identities: parsed.identities && typeof parsed.identities === "object"
                        ? parsed.identities
                        : {}
                };
            }
        } catch (error) {
            if (error.code !== "ENOENT") {
                console.error("Desktop offline store read error:", error);
            }
        }
    }

    save() {
        const dir = path.dirname(this.filePath);
        const temp = this.filePath + ".tmp";
        fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(temp, JSON.stringify(this.data), "utf8");
        fs.renameSync(temp, this.filePath);
    }

    identityKey(companyId, userId) {
        return String(companyId) + ":" + String(userId);
    }

    setActiveIdentity(profile) {
        const user = profile && profile.user && typeof profile.user === "object"
            ? profile.user
            : {};
        const companyId = Number(user.company_id || profile.company_id || 0);
        const userId = Number(user.id || profile.user_id || 0);
        if (!companyId || !userId) return null;

        const key = this.identityKey(companyId, userId);
        if (!this.data.identities[key]) {
            this.data.identities[key] = {
                company_id: companyId,
                user_id: userId,
                username: user.username || "",
                company_name: user.company_name || profile.company_name || "",
                last_sync_at: null,
                cache: {
                    profile: null,
                    items: [],
                    stock: [],
                    clients: [],
                    categories: [],
                    movements: [],
                    suppliers: []
                },
                queue: []
            };
        }

        const bucket = this.data.identities[key];
        bucket.company_id = companyId;
        bucket.user_id = userId;
        bucket.username = user.username || bucket.username || "";
        bucket.company_name = user.company_name || profile.company_name || bucket.company_name || "";
        bucket.cache = bucket.cache || {};
        bucket.cache.profile = profile;
        bucket.queue = Array.isArray(bucket.queue) ? bucket.queue : [];
        this.data.activeIdentity = key;
        this.save();
        return key;
    }

    clearActiveIdentity() {
        this.data.activeIdentity = null;
        this.save();
    }

    activeBucket() {
        const key = this.data.activeIdentity;
        return key ? (this.data.identities[key] || null) : null;
    }

    cache(name, value) {
        const bucket = this.activeBucket();
        if (!bucket) return;
        bucket.cache = bucket.cache || {};
        bucket.cache[name] = clone(value);
        this.save();
    }

    markSyncedNow() {
        const bucket = this.activeBucket();
        if (!bucket) return;
        bucket.last_sync_at = new Date().toISOString();
        this.save();
    }

    createOperation(operationType, requestPath, body) {
        const bucket = this.activeBucket();
        if (!bucket) {
            throw new Error("Нет локальной сессии. Один раз войдите в Nika Business с интернетом.");
        }

        const operation = {
            operation_id: "pc_" + Date.now() + "_" + crypto.randomUUID(),
            operation_type: operationType,
            method: "POST",
            path: requestPath,
            body: clone(body || {}),
            state: "pending",
            attempts: 0,
            last_error: null,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            optimistic_applied: false
        };
        bucket.queue.push(operation);
        this.save();
        return clone(operation);
    }

    pendingOperations(limit = 25) {
        const bucket = this.activeBucket();
        if (!bucket) return [];
        return bucket.queue
            .filter(op => op.state === "pending" || op.state === "syncing")
            .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))
            .slice(0, limit)
            .map(clone);
    }

    findOperation(operationId) {
        const bucket = this.activeBucket();
        if (!bucket) return null;
        return bucket.queue.find(op => op.operation_id === operationId) || null;
    }

    updateOperation(operationId, patch) {
        const operation = this.findOperation(operationId);
        if (!operation) return;
        Object.assign(operation, patch, { updated_at: new Date().toISOString() });
        this.save();
    }

    markSyncing(operationId) {
        this.updateOperation(operationId, { state: "syncing" });
    }

    markPending(operationId, error = null) {
        const operation = this.findOperation(operationId);
        if (!operation) return;
        operation.state = "pending";
        operation.attempts = Number(operation.attempts || 0) + 1;
        operation.last_error = error || null;
        operation.updated_at = new Date().toISOString();
        this.save();
    }

    markSynced(operationId) {
        this.updateOperation(operationId, { state: "synced", last_error: null });
    }

    markError(operationId, error) {
        const operation = this.findOperation(operationId);
        if (!operation) return;
        if (operation.optimistic_applied) this.rollbackOptimistic(operation);
        operation.state = "error";
        operation.attempts = Number(operation.attempts || 0) + 1;
        operation.last_error = String(error || "Ошибка синхронизации");
        operation.updated_at = new Date().toISOString();
        this.save();
    }

    updateCachedStock(itemId, delta) {
        const bucket = this.activeBucket();
        if (!bucket) return;
        const id = String(itemId);
        const lists = [
            bucket.cache && bucket.cache.stock,
            bucket.cache && bucket.cache.items
        ];
        for (const list of lists) {
            if (!Array.isArray(list)) continue;
            const item = list.find(row => String(row && row.id) === id);
            if (!item) continue;
            const current = asNumber(item.stock != null ? item.stock : item.quantity);
            const next = current + delta;
            item.stock = next;
            if (item.quantity != null) item.quantity = next;
        }
    }

    saleDelta(cart, direction) {
        const bucket = this.activeBucket();
        if (!bucket || !Array.isArray(cart)) return;
        for (const row of cart) {
            if (!row || typeof row !== "object") continue;
            const itemId = Number(row.id || 0);
            if (!itemId) continue;

            const cached = (bucket.cache.stock || []).find(
                item => String(item && item.id) === String(itemId)
            ) || (bucket.cache.items || []).find(
                item => String(item && item.id) === String(itemId)
            );
            const itemType = String(
                (cached && cached.item_type) || row.item_type || "product"
            );
            if (!["product", "ingredient", "semi_finished"].includes(itemType)) continue;

            const quantity = asNumber(row.qty != null ? row.qty : row.quantity);
            if (quantity > 0) this.updateCachedStock(itemId, direction * quantity);
        }
    }

    applyOptimistic(operationOrId) {
        const operation = typeof operationOrId === "string"
            ? this.findOperation(operationOrId)
            : this.findOperation(operationOrId.operation_id);
        if (!operation || operation.optimistic_applied) return;

        const body = operation.body || {};
        if (operation.operation_type === "sale") {
            this.saleDelta(body.cart || [], -1);
        } else if (
            operation.operation_type === "stock_income" ||
            operation.operation_type === "stock_income_supplier"
        ) {
            this.updateCachedStock(body.item_id, asNumber(body.quantity));
        } else if (operation.operation_type === "stock_writeoff") {
            this.updateCachedStock(body.item_id, -asNumber(body.quantity));
        }

        operation.optimistic_applied = true;
        operation.updated_at = new Date().toISOString();
        this.save();
    }

    rollbackOptimistic(operation) {
        const body = operation.body || {};
        if (operation.operation_type === "sale") {
            this.saleDelta(body.cart || [], 1);
        } else if (
            operation.operation_type === "stock_income" ||
            operation.operation_type === "stock_income_supplier"
        ) {
            this.updateCachedStock(body.item_id, -asNumber(body.quantity));
        } else if (operation.operation_type === "stock_writeoff") {
            this.updateCachedStock(body.item_id, asNumber(body.quantity));
        }
        operation.optimistic_applied = false;
    }

    state() {
        const bucket = this.activeBucket();
        if (!bucket) {
            return {
                ready: false,
                identity: null,
                cache: {
                    items: [],
                    stock: [],
                    clients: [],
                    categories: [],
                    movements: [],
                    suppliers: []
                },
                queue: [],
                pending_count: 0,
                last_sync_at: null
            };
        }

        const queue = (bucket.queue || []).filter(op => op.state !== "synced");
        return {
            ready: true,
            identity: {
                company_id: bucket.company_id,
                user_id: bucket.user_id,
                username: bucket.username || "",
                company_name: bucket.company_name || ""
            },
            cache: clone(bucket.cache || {}),
            queue: clone(queue),
            pending_count: queue.filter(
                op => op.state === "pending" || op.state === "syncing"
            ).length,
            last_sync_at: bucket.last_sync_at || null
        };
    }
}

module.exports = { DesktopOfflineStore };
