import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { Workflows } from './workflows';
import { WorkflowEntry, WorkflowStoreService } from '../../services/workflow-store';
import { NotificationService } from '../../services/notification';
import { TagService } from '../../services/tags';

const mockStore = {
  search: vi.fn().mockReturnValue(of({ items: [], metadata: {}, installed_version_ids: [] })),
  download: vi.fn(),
  list: vi.fn().mockReturnValue(of([])),
  deleteEntry: vi.fn(),
  exportWorkflow: vi.fn(),
  openInComfy: vi.fn(),
  fileUrl: vi.fn(),
};

function entry(): WorkflowEntry {
  return {
    id: 1,
    source_platform: 'civitai',
    source_page_id: '42',
    source_page_url: '',
    display_name: 'Some workflow',
    description: '',
    base_model: '',
    tags: [],
    thumbnail_url: '',
    media_hash: '',
    items: [],
    media: [],
  };
}

async function createFixture() {
  await TestBed.configureTestingModule({
    imports: [Workflows],
    providers: [
      { provide: WorkflowStoreService, useValue: mockStore },
      { provide: NotificationService, useValue: { show: vi.fn() } },
      { provide: TagService, useValue: { searchTags: vi.fn().mockReturnValue(of([])) } },
      provideTranslateServiceForTests(),
    ],
  }).compileComponents();
  return TestBed.createComponent(Workflows);
}

describe('Workflows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStore.list.mockReturnValue(of([]));
  });

  it('lists the installed tab before the browse tab', async () => {
    const fixture = await createFixture();
    fixture.detectChanges();
    const labels = [...fixture.nativeElement.querySelectorAll('.workflows-tab')].map(
      (b) => (b as HTMLElement).textContent?.trim() ?? '',
    );
    expect(labels).toEqual(['Installed', 'Browse CivitAI']);
  });

  it('opens on the browse tab when nothing is installed', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.activeTab()).toBe('browse');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('app-workflows-browse')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('app-workflows-installed')).toBeNull();
  });

  it('opens on the installed tab when at least one workflow is installed', async () => {
    mockStore.list.mockReturnValue(of([entry()]));
    const fixture = await createFixture();
    expect(fixture.componentInstance.activeTab()).toBe('installed');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('app-workflows-installed')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('app-workflows-browse')).toBeNull();
  });

  it('falls back to the browse tab when the list request fails', async () => {
    mockStore.list.mockReturnValue(throwError(() => new Error('boom')));
    const fixture = await createFixture();
    expect(fixture.componentInstance.activeTab()).toBe('browse');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('app-workflows-browse')).toBeTruthy();
  });

  it('switches to the installed tab', async () => {
    const fixture = await createFixture();
    fixture.componentInstance.activeTab.set('installed');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('app-workflows-installed')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('app-workflows-browse')).toBeNull();
  });
});
