import {
  Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions, Button,
} from '@mui/material'

export default function ConfirmDialog({
  open, title, message, onConfirm, onClose, confirmText = 'Confirm', confirmColor = 'primary',
}) {
  return (
    <Dialog open={open} onClose={onClose}>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent><DialogContentText>{message}</DialogContentText></DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={onConfirm} color={confirmColor} variant="contained">{confirmText}</Button>
      </DialogActions>
    </Dialog>
  )
}
