# SCL Encoding for the Anti-Bandwidth Problem

This document specifies the SCL encoding (Sequential Counter encoding for Ladder constraints) for the Anti-Bandwidth Problem (ABP) and its SAT implementation in PySAT.

---

## 1. Parameters and Variables

### Graph & Parameters
- **Graph**: Simple undirected graph $G = (V, E)$ with $V = \{1, \ldots, n\}$, $n \ge 2$, and $E \ne \varnothing$. Number of edges is $m = |E|$.
- **Label Set**: $Q = \{1, \ldots, n\}$.
- **Bandwidth Threshold**: Integer $2 \le w \le n$. The SAT decision formula asks whether there exists a bijection $\phi: V \to Q$ such that:
  $$\beta(\phi) = \min_{\{u,v\} \in E} |\phi(u) - \phi(v)| \ge w$$
  (Distance exactly $w$ is allowed; distance $< w$ is forbidden for every edge). Width $1$ is always feasible.

### Primary Boolean Variables
- **Assignment Variable**: $A_{v, \ell} \iff \text{vertex } v \text{ receives label } \ell$.
- **Indexing in PySAT**:
  $$\operatorname{id}(A_{v, \ell}) = (v - 1)n + \ell \quad (1 \le \operatorname{id} \le n^2)$$
- All auxiliary variables are allocated sequentially starting from $n^2 + 1$ using a single shared ID allocator.

---

## 2. Constraint Encoding

The formula enforces three requirements:
1. **Each label belongs to exactly one vertex** (Label EO).
2. **Each vertex receives exactly one label** (Vertex EO via block ladder).
3. **Adjacent vertices receive labels at least $w$ apart** (Edge sliding-window exclusions).

---

### 2.1 Label Constraints: 2-Product Exactly-One

For each label $\ell \in Q$:
$$\sum_{v \in V} A_{v, \ell} = 1$$

Encoded via a **2-Product Exactly-One** constraint over inputs $x_0, \ldots, x_{n-1}$ where $x_i = A_{i+1, \ell}$:

1. **Grid Dimensions**:
   $$p = \lceil\sqrt{n}\rceil, \qquad q = \lceil n/p\rceil$$
2. **Selectors**:
   - Row selectors: $r_0, \ldots, r_{p-1}$
   - Column selectors: $c_0, \ldots, c_{q-1}$
3. **Clauses**:
   - **Cell mapping** (each input activates its row and column):
     $$(\neg x_i \lor r_{i \bmod p}) \land (\neg x_i \lor c_{\lfloor i/p \rfloor}) \quad \text{for } 0 \le i < n$$
   - **At-least-one (ALO)**:
     $$\bigvee_{i=0}^{n-1} x_i$$
   - **At-most-one (AMO)** on selectors:
     $$\operatorname{AMO}(r_0, \ldots, r_{p-1}) \land \operatorname{AMO}(c_0, \ldots, c_{q-1})$$
4. **Base Case $n=2$**:
   - Emit directly: $(x_0 \lor x_1)$ and $(\neg x_0 \lor \neg x_1)$ with no auxiliary selector variables.

#### Sequential At-Most-One Chain
The selector AMOs use a sequential chain. For inputs $y_1, \ldots, y_t$ ($t \ge 2$):
- Set $s_1 = y_1$, introduce auxiliary variables $s_2, \ldots, s_{t-1}$.
- For each step $2 \le i \le t-1$, emit:
  $$(\neg s_{i-1} \lor \neg y_i), \qquad (\neg s_{i-1} \lor s_i), \qquad (\neg y_i \lor s_i)$$
- Final clause:
  $$\neg s_{t-1} \lor \neg y_t$$
- For $t = 2$, only the final clause $(\neg y_1 \lor \neg y_2)$ is needed. For $t < 2$, no clauses are needed.

---

### 2.2 Blocks and SCL Shared Interval Summaries

Partition label set $Q$ into $K = \lceil n/w \rceil$ consecutive blocks:
$$L_j = jw + 1, \qquad R_j = \min((j+1)w, n), \qquad B_j = \{L_j, \ldots, R_j\} \quad (0 \le j < K)$$

#### Interval Summaries
Define auxiliary variables representing disjunctions of assigned labels:
$$H_v[a, b] \iff \bigvee_{\ell=a}^b A_{v, \ell}$$

- **Singletons**: $H_v[a, a] \equiv A_{v, a}$ directly (reused, no auxiliary variable allocated).
- **Caching**: Each summary is cached by $(v, a, b)$ and allocated at most once across the entire formula.
- **Full Block Summary**: $F_{v, j} = H_v[L_j, R_j]$. Prefix and suffix ladders share the same full block variable.

#### Ladder Chains per Block $B_j$
For a vertex $v$:
1. **Prefix Chain** ($P_i = H_v[L_j, i]$ with $P_{L_j} = A_{v, L_j}$):
   - For $L_j < i \le R_j$, encode $P_i \leftrightarrow (P_{i-1} \lor A_{v, i})$:
     $$(\neg P_{i-1} \lor P_i), \qquad (\neg A_{v, i} \lor P_i), \qquad (P_{i-1} \lor A_{v, i} \lor \neg P_i)$$
   - Prefix AMO clause:
     $$\neg A_{v, i} \lor \neg P_{i-1}$$
2. **Suffix Chain** ($S_i = H_v[i, R_j]$ with $S_{R_j} = A_{v, R_j}$):
   - For $L_j \le i < R_j$, encode $S_i \leftrightarrow (A_{v, i} \lor S_{i+1})$:
     $$(\neg A_{v, i} \lor S_i), \qquad (\neg S_{i+1} \lor S_i), \qquad (A_{v, i} \lor S_{i+1} \lor \neg S_i)$$
   - Suffix AMO clause:
     $$\neg A_{v, i} \lor \neg S_{i+1}$$

#### Block Chain Selection
| Block Index | Clauses Generated |
|---|---|
| **First block** ($j = 0$) | Suffix equivalences + Suffix AMO |
| **Interior blocks** ($0 < j < K - 1$) | Prefix equivalences + Prefix AMO; Suffix equivalences (no suffix AMO needed) |
| **Final block** ($j = K - 1$, $K > 1$) | Prefix equivalences + Prefix AMO |
| **Single block** ($K = 1$) | Suffix equivalences + Suffix AMO |
| **Singleton blocks** ($L_j = R_j$) | No chain clauses required |

---

### 2.3 Vertex Constraints: Exactly One Occupied Block

For each vertex $v \in V$, let $F_{v, j} = H_v[L_j, R_j]$ be the full block summary:
1. **Block At-Least-One (ALO)**:
   $$\bigvee_{j=0}^{K-1} F_{v, j}$$
   *(Unit clause when $K = 1$)*
2. **Block Pairwise At-Most-One (AMO)**:
   $$\neg F_{v, j} \lor \neg F_{v, k} \qquad (0 \le j < k < K)$$

Since each occupied block enforces AMO internally, enforcing exactly one occupied block ensures each vertex receives **exactly one label overall**. These clauses replace a separate product exactly-one constraint over $A_{v, 1}, \ldots, A_{v, n}$.

---

### 2.4 Adjacent-Block Glue (Redundant Constraints)

For each vertex $v$ and adjacent blocks $B_j, B_{j+1}$ ($0 \le j < K - 1$):
- Let $d_{j+1} = R_{j+1} - L_{j+1} + 1$ be the size of block $B_{j+1}$.
- For each $1 \le i \le \min(w - 1, d_{j+1})$, emit:
  $$\neg H_v[L_j + i, R_j] \lor \neg H_v[L_{j+1}, L_{j+1} + i - 1]$$
- **Purpose**: These two intervals comprise $w$ consecutive labels spanning the block boundary. Although logically implied by the block AMO, adding these redundant clauses strengthens unit propagation.

---

### 2.5 Edge Constraints: Sliding-Window Exclusion

For an edge $\{u, v\} \in E$, any window $I_h = \{h, \ldots, h + w - 1\}$ of width $w$ ($1 \le h \le n - w + 1$) cannot contain both endpoints:
$$\neg\left(\bigvee_{\ell \in I_h} A_{u, \ell}\right) \lor \neg\left(\bigvee_{\ell \in I_h} A_{v, \ell}\right)$$

This is encoded without introducing any new edge variables:

1. **Aligned Window** ($I_h = B_j$, perfectly matches a full block):
   $$\neg F_{u, j} \lor \neg F_{v, j}$$
   *(1 clause per edge)*

2. **Crossing Window** ($I_h$ crosses boundary between $B_j$ and $B_{j+1}$):
   - Splits at block boundary into $D_1 = [h, R_j]$ and $D_2 = [L_{j+1}, h + w - 1]$.
   - Endpoint summaries:
     $$U_1 = H_u[h, R_j], \qquad U_2 = H_u[L_{j+1}, h + w - 1]$$
     $$V_1 = H_v[h, R_j], \qquad V_2 = H_v[L_{j+1}, h + w - 1]$$
   - Emit 4 clauses per edge:
     $$(\neg U_1 \lor \neg V_1), \qquad (\neg U_1 \lor \neg V_2), \qquad (\neg U_2 \lor \neg V_1), \qquad (\neg U_2 \lor \neg V_2)$$

*(Singleton summaries reuse assignment variables $A_{v, \ell}$ directly).*

---

## 3. Optional Symmetry Breaking

Label reversal $\phi'(v) = n + 1 - \phi(v)$ preserves all pairwise distances:
$$|\phi'(u) - \phi'(v)| = |(n + 1 - \phi(u)) - (n + 1 - \phi(v))| = |\phi(u) - \phi(v)|$$

To break this symmetry, select a fixed vertex $s$ and restrict it to the lower half of labels:
$$\neg A_{s, \ell} \qquad \left(\lceil n/2 \rceil < \ell \le n\right)$$
- Adds $\lfloor n/2 \rfloor$ unit clauses and $0$ variables.
- For odd $n$, the middle label remains unrestricted.

### Vertex Selection Modes
| Mode | Selected Vertex $s$ | Description |
|---|---|---|
| `n` | None | No symmetry breaking (default) |
| `f` | First | Vertex $1$ |
| `h` | High degree | Maximum-degree vertex (lowest index breaks ties) |
| `l` | Low degree | Minimum-degree vertex (lowest index breaks ties) |

---

## 4. PySAT Implementation & Generation Order

### Order of Construction
1. **Symmetry Breaking**: Add optional unit clauses $\neg A_{s, \ell}$.
2. **Label Constraints**: Add product exactly-one clauses for each label $\ell \in Q$.
3. **Vertex Constraints**: For each vertex $v \in V$:
   - Build block ladder chains.
   - Add adjacent-block glue clauses.
   - Add block ALO and block pairwise AMO clauses.
4. **Edge Constraints**: For each edge $\{u, v\} \in E$:
   - Add 1 clause for aligned windows.
   - Add 4 clauses for crossing windows.

### Solution Recovery & Validation
- Check solver status (`SAT` / `UNSAT`).
- When `SAT`, extract assignment: $\phi(v) = \ell$ where $A_{v, \ell} = \text{True}$.
- Validate:
  1. Exactly one label per vertex.
  2. Each label used exactly once (bijection).
  3. For every edge $\{u, v\} \in E$, $|\phi(u) - \phi(v)| \ge w$.

### Optimization & Search Bounds
- **Linear Search**: Start at a known feasible lower bound (e.g. $w = 2$) and increment $w$ by 1 until the first `UNSAT` result, using a fresh solver instance for each width.
- **Feasible Bounds**: Optimum is at most $n - 1$ since $E \ne \varnothing$; width $w = n$ is always `UNSAT`.
- **Upper Bound Without Isolated Vertices**: If minimum degree $\delta(G) \ge 1$:
  $$\beta(\phi) \le \lfloor n/2 \rfloor$$
  Hence, search limit $U = \lfloor n/2 \rfloor + 1$ is guaranteed `UNSAT`.
- **Graphs with Isolated Vertices**: Use $n - 1$ as valid upper limit.

---

## 5. Variable and Clause Counts

Let:
$$p = \lceil\sqrt{n}\rceil, \quad q = \lceil n/p\rceil, \quad K = \lceil n/w\rceil, \quad d = n - (K - 1)w$$
where $d$ is the length of the final block ($1 \le d \le w$).

### Per-Component Counts
1. **Product Exactly-One (per label)**:
   $$(a, c) = \begin{cases} (0, 2), & n = 2 \\ (2(p + q) - 4, \; 2n + 3(p + q) - 9), & n \ge 3 \end{cases}$$

2. **Vertex Ladder (per vertex)**:
   - Interval auxiliaries $\alpha$:
     $$\alpha = \begin{cases} n - 1, & K = 1 \\ (w - 1) + (K - 2)(2w - 3) + (d - 1), & K \ge 2 \end{cases}$$
   - Within-block ladder clauses $\lambda$:
     $$\lambda = \begin{cases} 4(n - 1), & K = 1 \\ 4(w - 1) + 7(K - 2)(w - 1) + 4(d - 1), & K \ge 2 \end{cases}$$
   - Adjacent-block glue clauses $\gamma$:
     $$\gamma = \begin{cases} 0, & K = 1 \\ (K - 2)(w - 1) + \min(w - 1, d), & K \ge 2 \end{cases}$$

3. **Edge Clauses (per edge)**:
   $$e = 4(n - w + 1) - 3\lfloor n/w \rfloor$$
   *(1 clause per aligned window, 4 clauses per crossing window)*

### Total Formula Size
$$\begin{aligned}
N &= n^2 + n(a + \alpha) \\
C &= n\left(c + \lambda + \gamma + \binom{K}{2} + 1\right) + m \cdot e
\end{aligned}$$

| Component | Variables | Clauses |
|---|---|---|
| Primary assignment variables | $n^2$ | $0$ |
| Product EO & selector chains | $n \cdot a$ | $n \cdot c$ |
| Interval summaries & within-block chains | $n \cdot \alpha$ | $n \cdot \lambda$ |
| Exactly one occupied block | $0$ | $n \left(\binom{K}{2} + 1\right)$ |
| Adjacent-block glue | $0$ | $n \cdot \gamma$ |
| Edge exclusions | $0$ | $m \cdot e$ |
| **Total (without symmetry breaking)** | **$N$** | **$C$** |
| **Total (with symmetry breaking)** | **$N$** | **$C + \lfloor n/2 \rfloor$** |

### Example Verification
For $n = 6$, $m = 6$, and $w = 3$:
- $p = 3$, $q = 2 \implies a = 6$, $c = 18$
- $K = 2$, $d = 3 \implies \alpha = 4$, $\lambda = 16$, $\gamma = 2$, $\binom{K}{2} + 1 = 2$
- $e = 4(6 - 3 + 1) - 3\lfloor 6/3 \rfloor = 16 - 6 = 10$
- **Total Variables**: $N = 36 + 6(6 + 4) = 96$
- **Total Clauses**: $C = 6(18 + 16 + 2 + 2) + 6(10) = 228 + 60 = 288$ ($291$ with symmetry breaking)

### Asymptotic Complexity
- **Variables**: $O(n^2)$
- **Clauses**: $O\left(n^2 + n \lceil n/w \rceil^2 + m(n - w + 1)\right)$
