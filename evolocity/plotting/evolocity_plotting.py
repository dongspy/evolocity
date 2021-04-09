from .. import logging as logg
from ..tools.velocity_embedding import quiver_autoscale, velocity_embedding

from anndata import AnnData
import matplotlib.pyplot as plt
import numpy as np
import scanpy as sc
import scipy.stats as ss
import seaborn as sns

def shortest_path(
        adata,
        source_idx,
        target_idx,
        vkey='velocity',
):
    if np.min((get_neighs(adata, 'distances') > 0).sum(1).A1) == 0:
        raise ValueError(
            'Your neighbor graph seems to be corrupted. '
            'Consider recomputing via scanpy.pp.neighbors.'
        )

    if f'{vkey}_graph' not in adata.uns:
        raise ValueError(
            'Must run velocity_graph() first.'
        )

    T = adata.uns[f'{vkey}_graph'] - adata.uns[f'{vkey}_graph_neg']

    import networkx as nx

    G = nx.convert_matrix.from_scipy_sparse_matrix(T)

    path = nx.algorithms.shortest_paths.generic.shortest_path(
        G, source=source_idx, target=target_idx,
    )

    return path


def draw_path(
        adata,
        path=None,
        source_idx=None,
        target_idx=None,
        basis='umap',
        vkey='velocity',
        ax=None,
        color='white',
        cmap=None,
        size=15,
        edgecolor='black',
        linecolor='#888888',
        linewidth=0.001,
):
    if path is None and (source_idx is None or target_idx is None):
        raise ValueError(
            'Must provide path indices or source and target indices.'
        )

    if path is None:
        path = shortest_path(adata, source_idx, target_idx, vkey=vkey)

    if ax is None:
        plt.figure()
        ax = plt.gca()

    if f'X_{basis}' not in adata.obsm:
        raise ValueError(
            f'Basis {basis} not found in AnnData.'
        )

    basis_x = np.array(adata.obsm[f'X_{basis}'][path, 0]).ravel()
    basis_y = np.array(adata.obsm[f'X_{basis}'][path, 1]).ravel()

    for idx, (x, y) in enumerate(zip(basis_x, basis_y)):
        if idx < len(basis_x) - 1:
            dx, dy = basis_x[idx + 1] - x, basis_y[idx + 1] - y
            ax.arrow(x, y, dx, dy, width=linewidth, head_width=0,
                     length_includes_head=True,
                     color=linecolor, zorder=5)

    ax.scatter(basis_x, basis_y,
               s=size, c=color, cmap=cmap,
               edgecolors=edgecolor, linewidths=0.5, zorder=10)

    return ax


def residue_scores(
        adata,
        percentile_keep=0.,
        basis='onehot',
        key='residue_scores',
        cmap='RdBu',
        save=None,
):
    scores = AnnData(adata.uns[key])

    vocab = adata.uns[f'{basis}_vocabulary']
    scores.var_names = [
        vocab[key] for key in sorted(vocab.keys())
    ]

    positions = [ str(x) for x in range(scores.X.shape[0]) ]
    scores.obs['position'] = positions

    if percentile_keep > 0:
        score_sum = np.abs(scores.X).sum(1)
        cutoff = np.percentile(score_sum, percentile_keep)
        scores = scores[score_sum >= cutoff]

    end = max(abs(np.min(scores.X)), np.max(scores.X)) # Zero-centered colors.
    scores.X /= end # Scale within -1 and 1, inclusive.

    plt.figure(figsize=(
        max(scores.X.shape[1] // 2, 5),
        max(scores.X.shape[0] // 20, 5)
    ))
    sns.heatmap(
        scores.X,
        xticklabels=scores.var_names,
        yticklabels=scores.obs['position'],
        cmap=cmap,
        vmin=-1.,
        vmax=1.,
    )

    if save is not None:
        plt.savefig('figures/evolocity_' + save)
        plt.close()
    else:
        ax = plt.gca()
        return ax

def residue_categories(
        adata,
        positions=None,
        n_plot=5,
        namespace='residue_categories',
        reference=None,
        verbose=True,
):
    if reference is not None:
        seq_ref = adata.obs['seq'][reference]
        seq_ref_msa = adata.obs['seqs_msa'][reference]
        pos2msa, ref_idx = {}, 0
        for idx, ch in enumerate(seq_ref_msa):
            if ch == '-':
                continue
            assert(ch == seq_ref[ref_idx])
            pos2msa[ref_idx] = idx
            ref_idx += 1

    if positions is None:
        scores = adata.uns['residue_scores']
        pos_seen = set()
        while len(pos_seen) < n_plot:
            min_idx = np.unravel_index(np.argmin(scores), scores.shape)
            scores[min_idx] = float('inf')
            aa = adata.uns['onehot_vocabulary'][min_idx[1]]
            pos = min_idx[0]
            if pos in pos_seen:
                continue
            pos_seen.add(pos)
            if verbose:
                logg.info('Lowest score {}: {}{}'.format(len(pos_seen), aa, pos + 1))
        positions = sorted(pos_seen)

    for pos in positions:
        adata.obs[f'pos{pos}'] = [
            seq[pos] if reference is None else seq[pos2msa[pos]]
            for seq in adata.obs['seqs_msa']
        ]
        sc.pl.umap(adata, color=f'pos{pos}', save=f'_{namespace}_pos{pos}.png',
                   edges=True,)
