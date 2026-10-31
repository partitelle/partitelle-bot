from telegram import LinkPreviewOptions

WELCOME_TEXT = (
    "Ciao bestie 😎, chi c'è per il prossimo calcetto? \n"
    "\n"
    "- se sei in forse scrivi _proponimi_, \n"
    "- se vuoi proporre qualcuno scrivi _proponi <nome>_, \n"
    "- per essere aggiunto o confermato rispondi _aggiungimi_,\n"
    "- per aggiungere o confermare qualcuno usa _aggiungi <nome>_,\n"
    "- per essere rimosso _toglimi_, \n"
    "- per rimuovere qualcuno _togli <nome>_, \n"
    "- per modificare le squadre scrivi _scambia <nome 1> con <nome 2>_. \n\n"
    "Posso anche pinnare i messaggi se vuoi "
    "ma per farlo ricordati di aggiungermi come amministratore.\n"
    "\n"
    "Come usiamo i tuoi dati: https://partitelle.com/privacy"
)
NO_LINK_PREVIEW = LinkPreviewOptions(is_disabled=True)
