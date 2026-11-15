"""Rendering only: original pixels at WCS positions, shared Time Explorer controls."""
import numpy as np
from astropy.time import Time
from matplotlib.figure import Figure
from matplotlib.cm import ScalarMappable
from matplotlib.patches import Circle

from . import non_sidereal as ns, player, render


@render.serialized
def frame_png(frame,fov,norm,centre=None):
    img=frame.image
    p=frame.prediction
    centre=centre or (p['ra'],p['dec'])
    w,shape=ns.grid(*centre,fov)
    yy,xx=np.indices((img.shape[0]+1,img.shape[1]+1),dtype=float)
    ra,dec=img.wcs.all_pix2world(xx-.5,yy-.5,0)
    sx,sy=w.all_world2pix(ra,dec,0)
    fig=Figure(figsize=(6.8,6.6),dpi=110,facecolor='white')
    ax=fig.add_axes([.12,.16,.80,.77])
    ax.set_facecolor('#f2eaf5')
    data=np.where(img.valid(),img.image-img.zodi,np.nan)
    rgba=render.native_rgba(data,norm)
    render.draw_native(ax,(sx,sy),rgba,shape)
    ax.add_patch(Circle(((shape[1]-1)/2,(shape[0]-1)/2),fov*3600/6.15/2,
                       fill=False,edgecolor='#c4411c',linestyle='--',linewidth=.7,alpha=.6))
    tx,ty=w.all_world2pix(p['ra'],p['dec'],0)
    if -.5<=tx<shape[1]-.5 and -.5<=ty<shape[0]-.5:
        ax.plot(tx,ty,'+',color='#c4411c',ms=12,mew=1.4)
    ticks=np.linspace(0,shape[0]-1,5)
    ax.set_xticks(ticks,[f'{(t-(shape[1]-1)/2)*-6.15:.0f}' for t in ticks])
    ax.set_yticks(ticks,[f'{(t-(shape[0]-1)/2)*6.15:.0f}' for t in ticks])
    ax.set_xlabel('Este (″)');ax.set_ylabel('Norte (″)')
    ax.set_title(Time(frame.row['mjd'],format='mjd').isot[:19]+' UTC',fontsize=12)
    ax.tick_params(labelsize=9)
    cb=fig.colorbar(ScalarMappable(norm=norm,cmap=render._cmap()),cax=fig.add_axes([.22,.055,.6,.025]),orientation='horizontal')
    cb.set_label('IMAGE − ZODI · MJy/sr',fontsize=9)
    cb.ax.tick_params(labelsize=8)
    return render.figure_png(fig)


def build(frames,fov,follow=True,simple=True,animate=True):
    # Normalization only over the requested displayed field, not extra sky context.
    arrays,_,_=ns.aligned(frames,fov,follow)
    norm=render.shared_norm(arrays,lo=5,hi=99)
    p0=frames[0].prediction
    pngs=[frame_png(f,fov,norm,None if follow else (p0['ra'],p0['dec'])) for f in frames]
    meta=[{'i':i,'date':Time(f.row['mjd'],format='mjd').isot[:19].replace('T',' ')+' UTC',
           'dt_days':f.row['mjd']-frames[0].row['mjd'],'obs_id':f.row['obs_id'],
           'collection':f.row['collection'],'detector':f.row['detector'],
           'lambda_um':f.row['lambda_um'],'valid_pct':float(np.isfinite(arrays[i])[ns.requested_field(arrays[i].shape,fov)].mean()*100),
           'file':f.row['url'].rsplit('/',1)[-1]} for i,f in enumerate(frames)]
    legend=('Cruz terracota: posición prevista, no detección. Rosa: píxeles enmascarados; lila: sin cobertura. '
            +('Cada imagen sigue la posición prevista del objeto.' if follow else 'Fondo fijo según WCS.')+
            ' Imágenes originales, misma escala de brillo; sin suavizado.' )
    return player.observation_player(pngs,meta,legend,simple,animate)


@render.serialized
def stack_figure(follow,control):
    fig=Figure(figsize=(10,4.8),dpi=110,facecolor='white')
    norm=render.shared_norm([follow['image'],control['image']],lo=5,hi=99)
    for i,(product,title) in enumerate(((follow,'Siguiendo la predicción'),(control,'Control: fondo fijo'))):
        ax=fig.add_subplot(1,2,i+1)
        ax.imshow(product['image'],origin='lower',interpolation='nearest',norm=norm,cmap=render._cmap())
        ax.set_title(title,fontsize=11);ax.set_xlabel('Píxel de la rejilla común')
    fig.suptitle('Apilamientos exploratorios · remuestreados · IMAGE − ZODI − fondo',fontsize=11)
    return fig
